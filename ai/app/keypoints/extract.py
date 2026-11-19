"""Turn a local phone video into normalized, timestamped pose landmarks."""

import contextlib
import tempfile
from pathlib import Path
from typing import Any

import cv2

from .pose import create_landmarker, detect, draw_skeleton, frame_json
from .video import TARGET_FPS, OverlayWriter, VideoError, normalize

# ai/models/, wherever the command runs (/app/models in the Docker image). The model
# is not in git: ai/download_model.py saves it here (a test checks the two agree).
DEFAULT_MODEL = Path(__file__).resolve().parents[2] / "models/pose_landmarker_full.task"


def extract_keypoints(
    video: Path, model: Path, overlay_path: Path | None = None
) -> dict[str, Any]:
    """Return JSON-ready frames; write a debug overlay only when requested.

    ffmpeg handles phone codecs and rotation before OpenCV sees the video. The
    returned data contains no input path. The temporary normalized file is
    removed even when decoding or pose detection fails. Raises VideoError when the
    video cannot be used, and VideoTimeoutError when ffmpeg takes too long.
    """
    # The model loads first, so a missing model fails before minutes of encoding.
    with (
        create_landmarker(model) as landmarker,
        tempfile.TemporaryDirectory() as temp_dir,
    ):
        normalized = Path(temp_dir) / "normalized.mp4"
        normalize(video, normalized)

        capture = cv2.VideoCapture(str(normalized))
        try:
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if width <= 0 or height <= 0:
                raise VideoError("The video has no readable frames")

            frames = []
            with (
                OverlayWriter(overlay_path, width, height)
                if overlay_path is not None
                else contextlib.nullcontext()
            ) as overlay:
                while True:
                    ok, image = capture.read()
                    if not ok:
                        break
                    index = len(frames)
                    timestamp_ms = round(index * 1000 / TARGET_FPS)
                    frame = frame_json(
                        index, TARGET_FPS, detect(landmarker, image, timestamp_ms)
                    )
                    if overlay is not None:
                        draw_skeleton(image, frame["landmarks"], frame["time_seconds"])
                        overlay.write(image)
                    frames.append(frame)
                # Inside the overlay block, so an empty overlay cannot hide this.
                if not frames:
                    raise VideoError("The video has no readable frames")
        finally:
            capture.release()

    return {
        "video": {
            "width": width,
            "height": height,
            "fps": float(TARGET_FPS),
            "frame_count": len(frames),
        },
        "model": model.name,
        "frames": frames,
    }
