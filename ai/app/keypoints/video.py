"""ffmpeg steps: normalize the input video, and write the debug overlay video."""

import subprocess
from pathlib import Path

import numpy as np

# PT reps take 2 seconds or more, so 15 frames per second is plenty, and it halves
# MediaPipe's time compared with 30.
TARGET_FPS = 15
# MediaPipe shrinks every image to a small size internally, so larger frames only
# cost time. Smaller videos are never scaled up.
MAX_SIDE_PIXELS = 1280


class VideoError(Exception):
    """ffmpeg could not read the input video or write the overlay video."""


def normalize_command(source: Path, target: Path) -> list[str]:
    """The ffmpeg arguments that turn any video into an upright H.264 MP4.

    Keeps only the first video stream (no audio), sets a constant TARGET_FPS, and
    scales the longer side down to MAX_SIDE_PIXELS with even dimensions. ffmpeg
    applies phone rotation metadata itself, before these filters. The veryfast
    preset encodes about twice as fast as the default, and the file is temporary.
    """
    limit = MAX_SIDE_PIXELS
    filters = (
        f"fps={TARGET_FPS},"
        f"scale=w='min({limit},iw)':h='min({limit},ih)'"
        ":force_original_aspect_ratio=decrease:force_divisible_by=2"
    )
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-autorotate", "-i", str(source),
        "-map", "0:v:0",
        "-vf", filters,
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        str(target),
    ]  # fmt: skip


def normalize(source: Path, target: Path) -> None:
    """Run ffmpeg to write the normalized video. Raises VideoError if it fails."""
    process = subprocess.run(
        normalize_command(source, target), capture_output=True, text=True
    )
    if process.returncode != 0:
        # ffmpeg stderr can include the input path or metadata with personal data.
        raise VideoError("ffmpeg could not read the input video")


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
    """Pipes frames into ffmpeg, which writes the overlay video."""

    def __init__(self, target: Path, width: int, height: int) -> None:
        self._process = subprocess.Popen(
            overlay_command(target, width, height), stdin=subprocess.PIPE
        )

    def write(self, image: np.ndarray) -> None:
        """Add one BGR frame, the same size as given to the constructor."""
        self._process.stdin.write(image.tobytes())

    def close(self) -> None:
        """Finish the file. Raises VideoError if ffmpeg failed."""
        self._process.stdin.close()
        if self._process.wait() != 0:
            raise VideoError("ffmpeg could not write the overlay video")
