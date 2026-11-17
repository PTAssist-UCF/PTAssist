"""Upload checks: the size limit while an upload arrives, then the received file's
type, size, and length. Storage access stays in app/storage/."""

import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import MAX_VIDEO_UPLOAD_BYTES
from app.schemas.analysis_contract import (
    ERROR_MESSAGES,
    MAX_VIDEO_SECONDS,
    MIN_VIDEO_SECONDS,
)

VIDEO_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}
# MP4 and QuickTime (MOV) are one container family, and phones name them loosely: a
# ".mov" file can hold an ISO MP4, and the other way round. Either name is accepted for
# either one; the blob gets the type of the inspected container. WebM is separate.
MOV_FAMILY = {".mp4", ".mov"}
PROBE_TIMEOUT_SECONDS = 15

WRONG_TYPE = "Upload an MP4, MOV, or WebM video"
WRONG_EXTENSION = "The video format does not match its file extension"

# The first bytes of the supported containers. An MP4 or QuickTime file is a series of
# boxes, each starting with its size (4 bytes) and its type (4 letters). Phones and
# browsers write "ftyp" first; older QuickTime files can start with one of the others.
# WebM is Matroska, which starts with the EBML magic number.
MOV_FIRST_BOXES = {b"ftyp", b"moov", b"mdat", b"free", b"skip", b"wide", b"pnot"}
EBML_MAGIC = b"\x1a\x45\xdf\xa3"

# Room in an upload request for everything but the video: the plan exercise id, the
# multipart boundaries and headers, and the file name. The web app sends a few hundred
# bytes. 1 MiB is also the most Starlette accepts in one form field.
FORM_OVERHEAD_BYTES = 1024**2


def too_large_message() -> str:
    """The 413 answer for a video over MAX_VIDEO_UPLOAD_BYTES. The web app shows it.

    Sizes are in MB of 1024 * 1024 bytes, as the web app shows a file's size.
    """
    return (
        f"Video exceeds the {MAX_VIDEO_UPLOAD_BYTES // 1024**2} MB limit. "
        "Please record a shorter or lower-resolution video."
    )


class UploadSizeLimitMiddleware:
    """Stops reading an upload (POST /sessions) once it is larger than the limit.

    FastAPI reads the whole form, spooling the video to temporary disk, before the
    route and its dependencies run, sign-in included. So without this, anyone could
    make the API write as much as they send. A request may be at most
    MAX_VIDEO_UPLOAD_BYTES plus FORM_OVERHEAD_BYTES: a larger Content-Length is
    refused before the body is read, and a body sent without one (chunked) is cut off
    as soon as it passes the limit. Either way the answer is 413, and Starlette closes
    and deletes what it had spooled. validate_video then checks the video's own size.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _is_upload(scope):
            await self.app(scope, receive, send)
            return
        limit = MAX_VIDEO_UPLOAD_BYTES + FORM_OVERHEAD_BYTES
        try:
            declared = int(Headers(scope=scope).get("content-length", ""))
        except ValueError:
            declared = 0  # no Content-Length (a chunked body), or a malformed one
        if declared > limit:
            response = JSONResponse({"detail": too_large_message()}, status_code=413)
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # FastAPI answers an HTTPException raised while it reads the body
                    # the same way as one raised in the route: 413 with this detail.
                    raise HTTPException(413, too_large_message())
            return message

        await self.app(scope, limited_receive, send)


def _is_upload(scope: Scope) -> bool:
    """Whether the request is POST /sessions. A server started with a root path
    (uvicorn --root-path) puts it in front of the path."""
    return (
        scope["type"] == "http"
        and scope["method"] == "POST"
        and scope["path"] == scope.get("root_path", "") + "/sessions"
    )


@dataclass(frozen=True)
class VideoInfo:
    extension: str
    content_type: str


def validate_video(video: UploadFile) -> VideoInfo:
    """Validate actual file size and media metadata, then rewind for storage.

    The file name is used only for its extension, never in a path or a log line.
    """
    extension = Path(video.filename or "").suffix.lower()
    if extension not in VIDEO_TYPES or video.content_type not in (
        *VIDEO_TYPES.values(),
        "application/octet-stream",
        None,
    ):
        raise HTTPException(415, WRONG_TYPE)
    size = video.file.seek(0, 2)
    video.file.seek(0)
    if size > MAX_VIDEO_UPLOAD_BYTES:
        raise HTTPException(413, too_large_message())
    if not size:
        raise HTTPException(422, ERROR_MESSAGES["video_unreadable"])
    # The first bytes must be a video's, of the type the extension names, before the
    # file is copied and given to ffprobe. A renamed photo or document stops here.
    fits = _extensions_by_first_bytes(video)
    if not fits:
        raise HTTPException(415, WRONG_TYPE)
    if extension not in fits:
        raise HTTPException(415, WRONG_EXTENSION)

    # ffprobe needs seeking for phone MP4/MOV files with metadata at the end.
    # Work on a temporary local file, copy in bounded chunks, and always remove it.
    try:
        with tempfile.TemporaryDirectory(prefix="ptassist-upload-") as directory:
            path = Path(directory) / "video"
            with path.open("wb") as target:
                shutil.copyfileobj(video.file, target, length=4 * 1024 * 1024)
            metadata = _probe(path)
    except OSError:
        raise HTTPException(
            503, "Video validation is temporarily unavailable"
        ) from None
    finally:
        video.file.seek(0)

    try:
        streams = [
            stream
            for stream in metadata["streams"]
            if stream.get("codec_type") == "video"
            and not stream.get("disposition", {}).get("attached_pic", 0)
        ]
        if not streams:
            raise ValueError("No video stream")
        container = metadata["format"]
        format_names = container["format_name"].split(",")
        is_webm = "webm" in format_names or "matroska" in format_names
        is_mov = "mov" in format_names
        if not (is_webm or is_mov):
            raise ValueError("Unsupported container")
        # Read a fixed, trusted content type from the inspected container, never
        # use a user-supplied MIME type as the blob's content type.
        if is_webm:
            actual = VideoInfo(".webm", "video/webm")
        elif container.get("tags", {}).get("major_brand", "").strip() == "qt":
            actual = VideoInfo(".mov", "video/quicktime")
        else:
            actual = VideoInfo(".mp4", "video/mp4")
        if actual.extension != extension and not (
            actual.extension in MOV_FAMILY and extension in MOV_FAMILY
        ):
            raise HTTPException(415, WRONG_EXTENSION)

        container_duration = float(container["duration"])
        durations = [float(s["duration"]) for s in streams if s.get("duration")]
        duration = max(durations) if durations else container_duration
        if not all(
            math.isfinite(x) and x > 0 for x in [container_duration, *durations]
        ):
            raise ValueError("Unknown duration")
    except (KeyError, ValueError, TypeError, AttributeError):
        raise HTTPException(422, ERROR_MESSAGES["video_unreadable"]) from None
    if duration < MIN_VIDEO_SECONDS:
        raise HTTPException(422, ERROR_MESSAGES["too_short"])
    if max(duration, container_duration) > MAX_VIDEO_SECONDS:
        raise HTTPException(422, ERROR_MESSAGES["too_long"])
    return actual


def _extensions_by_first_bytes(video: UploadFile) -> set[str]:
    """The extensions that fit the file's first bytes: the MP4 and MOV family, .webm,
    or none for a file that is not one of our videos. Rewinds the file.

    A quick check of the file's type only: ffprobe still inspects the whole container.
    """
    head = video.file.read(8)
    video.file.seek(0)
    if head.startswith(EBML_MAGIC):
        return {".webm"}
    if head[4:8] in MOV_FIRST_BOXES:
        return MOV_FAMILY
    return set()


def _probe(path: Path) -> dict:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file",
                "-format_whitelist",
                "mov,matroska,webm",
                "-show_entries",
                "format=format_name,duration:format_tags=major_brand:"
                "stream=codec_type,duration:stream_disposition=attached_pic",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=True,
        )
        return json.loads(result.stdout)
    except FileNotFoundError:
        raise HTTPException(503, "Video validation is not configured") from None
    except subprocess.TimeoutExpired:
        # Our side was too slow (for example a busy server), which says nothing about
        # the video, so don't ask the patient to record it again.
        raise HTTPException(
            503, "Checking the video took too long. Please try again."
        ) from None
    except (subprocess.SubprocessError, ValueError):
        # ffprobe errors can contain filenames or media metadata: never return or
        # log its output. All child processes have a bounded execution time.
        raise HTTPException(422, ERROR_MESSAGES["video_unreadable"]) from None
