"""Inspect temporary upload files; storage access stays in app/storage/."""

import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import MAX_VIDEO_UPLOAD_BYTES
from app.schemas.analysis_contract import (
    ERROR_MESSAGES,
    MAX_VIDEO_SECONDS,
    MIN_VIDEO_SECONDS,
)

VIDEO_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}
PROBE_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class VideoInfo:
    extension: str
    content_type: str


def validate_video(video: UploadFile) -> VideoInfo:
    """Validate actual file size and media metadata, then rewind for storage."""
    extension = Path(video.filename or "").suffix.lower()
    if extension not in VIDEO_TYPES or video.content_type not in (
        *VIDEO_TYPES.values(),
        "application/octet-stream",
        None,
    ):
        raise HTTPException(415, "Upload an MP4, MOV, or WebM video")
    size = video.file.seek(0, 2)
    video.file.seek(0)
    if size > MAX_VIDEO_UPLOAD_BYTES:
        raise HTTPException(
            413, f"Video exceeds the {MAX_VIDEO_UPLOAD_BYTES}-byte limit"
        )
    if not size:
        raise HTTPException(422, ERROR_MESSAGES["video_unreadable"])

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
        if actual.extension != extension:
            raise HTTPException(
                415, "The video format does not match its file extension"
            )

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
    except (subprocess.SubprocessError, ValueError):
        # ffprobe errors can contain filenames or media metadata: never return or
        # log its output. All child processes have a bounded execution time.
        raise HTTPException(422, ERROR_MESSAGES["video_unreadable"]) from None
