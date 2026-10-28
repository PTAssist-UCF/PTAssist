"""ffmpeg steps: normalize the input video, and write the debug overlay video."""

import contextlib
import logging
import subprocess
from pathlib import Path
from types import TracebackType

import numpy as np

from app.analysis_contract import MAX_VIDEO_SECONDS

logger = logging.getLogger(__name__)

# PT reps take 2 seconds or more, so 15 frames per second is plenty, and it halves
# MediaPipe's time compared with 30.
TARGET_FPS = 15
# MediaPipe shrinks every image to a small size internally, so larger frames only
# cost time. Smaller videos are never scaled up.
MAX_SIDE_PIXELS = 1280
# ffmpeg stops reading just past the longest video we analyze, so an over-long upload
# is never processed in full. Nothing rejects it yet: SCRUM-73 fails a video as
# too_long when its keypoint data holds more than MAX_VIDEO_SECONDS of frames
# (frame_count / fps). The extra second is what lets that check see "too long".
MAX_NORMALIZED_SECONDS = MAX_VIDEO_SECONDS + 1
# Normalizing a capped video takes well under a minute on one CPU; give up long after.
NORMALIZE_TIMEOUT_SECONDS = 300
# The most of ffmpeg's error output that is logged (see normalize).
MAX_LOGGED_ERROR_CHARS = 200


class VideoError(Exception):
    """The video itself cannot be used: ffmpeg cannot decode it, or it has no frames.

    Callers may ask the patient to record again (the video_unreadable error), so raise
    it only for problems with the video, never for problems on our side.
    """


class VideoTimeoutError(Exception):
    """ffmpeg took too long to normalize the video.

    Not a VideoError: the video may be fine and the server slow, so the patient must
    not be asked to record again. Not a TimeoutError either, because that is an
    OSError, and an `except OSError` for file problems must not catch it.
    """


class OverlayError(Exception):
    """ffmpeg could not write the debug overlay. Our output failed, not the video."""


def normalize_command(source: Path, target: Path) -> list[str]:
    """The ffmpeg arguments that turn any video into an upright H.264 MP4.

    Keeps only the first video stream (no audio) and its first MAX_NORMALIZED_SECONDS,
    sets a constant TARGET_FPS, and scales the longer side down to MAX_SIDE_PIXELS
    with even dimensions. ffmpeg applies phone rotation metadata by default, before
    these filters. Do not add -autorotate: ffmpeg 6.1 and older expect a value after
    it, so it would swallow the -i. The veryfast preset encodes about twice as fast
    as the default, and the file is temporary.
    """
    limit = MAX_SIDE_PIXELS
    filters = (
        f"fps={TARGET_FPS},"
        f"scale=w='min({limit},iw)':h='min({limit},ih)'"
        ":force_original_aspect_ratio=decrease:force_divisible_by=2"
    )
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(source),
        "-map", "0:v:0", "-t", str(MAX_NORMALIZED_SECONDS),
        "-vf", filters,
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        str(target),
    ]  # fmt: skip


def normalize(source: Path, target: Path) -> None:
    """Run ffmpeg to write the normalized video.

    Raises VideoError if ffmpeg cannot read the video, and VideoTimeoutError if it
    runs longer than NORMALIZE_TIMEOUT_SECONDS. Neither message holds the input path,
    which could contain a patient's name.
    """
    try:
        process = subprocess.run(
            normalize_command(source, target),
            capture_output=True,
            text=True,
            # ffmpeg can print bytes the locale cannot decode (file names, metadata);
            # a strict decode would crash here instead of reporting the failure.
            errors="replace",
            timeout=NORMALIZE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # "from None": the timeout error's text holds the command, input path included.
        raise VideoTimeoutError("ffmpeg took too long to normalize the video") from None
    if process.returncode != 0:
        logger.warning(
            "ffmpeg exited with code %s: %s",
            process.returncode,
            _last_error_line(process.stderr, source),
        )
        raise VideoError("ffmpeg could not read the input video")


def _last_error_line(stderr: str, source: Path) -> str:
    """ffmpeg's final error line, without the input path, for the logs.

    The last line says why ffmpeg failed (for example "Invalid data found when
    processing input"). ffmpeg writes the input path, exactly as it was passed, as
    a prefix ("path: message", ffmpeg 6), after "input file " (ffmpeg 7), or in
    quotes; only those forms are replaced, so a short file name such as "video"
    cannot mangle the words of the message.
    """
    lines = [line for line in stderr.splitlines() if line.strip()]
    if not lines:
        return "no details"
    line, path = lines[-1], str(source)
    if line.startswith(f"{path}:"):
        line = "<input>" + line[len(path) :]
    redactions = {
        f"input file {path}": "input file <input>",
        f"'{path}'": "<input>",
        f'"{path}"': "<input>",
    }
    for found, replacement in redactions.items():
        line = line.replace(found, replacement)
    return line[:MAX_LOGGED_ERROR_CHARS]


def overlay_command(target: Path, width: int, height: int) -> list[str]:
    """The ffmpeg arguments that encode raw BGR frames from stdin as H.264 MP4.

    H.264 with yuv420p plays in browsers and in Windows' built-in player.
    """
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{width}x{height}", "-r", str(TARGET_FPS),
        "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        str(target),
    ]  # fmt: skip


class OverlayWriter:
    """Pipes frames into ffmpeg, which writes the overlay video. Use it in `with`."""

    def __init__(self, target: Path, width: int, height: int) -> None:
        self._process = subprocess.Popen(
            overlay_command(target, width, height), stdin=subprocess.PIPE
        )

    def write(self, image: np.ndarray) -> None:
        """Add one BGR frame, the same size as given to the constructor."""
        self._process.stdin.write(image.tobytes())

    def __enter__(self) -> "OverlayWriter":
        return self

    def __exit__(
        self,
        error_type: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Finish the file, or, if an error is on its way out, just stop ffmpeg.

        Stopping quietly keeps the original error visible: an overlay that is
        unfinished anyway must not replace it with its own failure.
        """
        if error_type is not None:
            self._process.kill()
            with contextlib.suppress(OSError):  # ffmpeg may have closed the pipe
                self._process.stdin.close()
            self._process.wait()
            return
        # If ffmpeg already exited, closing fails: BrokenPipeError on Linux, but
        # OSError (EINVAL) on Windows. Either way, the exit code below says why.
        with contextlib.suppress(OSError):
            self._process.stdin.close()
        if self._process.wait() != 0:
            raise OverlayError("ffmpeg could not write the overlay video")
