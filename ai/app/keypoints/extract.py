"""Turn a local phone video into normalized, timestamped pose landmarks."""

import tempfile
from pathlib import Path
from typing import Any

import cv2

from .pose import create_landmarker, detect, draw_skeleton, frame_json
from .video import TARGET_FPS, OverlayWriter, VideoError, normalize


def extract_keypoints(
    video: Path, model: Path, overlay_path: Path | None = None
) -> dict[str, Any]:
    """Return JSON-ready frames; write a debug overlay only when requested.

    ffmpeg handles phone codecs and rotation before OpenCV sees the video. The
    returned data contains no input path. The temporary normalized file is
    removed even when decoding or pose detection fails.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        normalized = Path(temp_dir) / "normalized.mp4"
        normalize(video, normalized)

        capture = cv2.VideoCapture(str(normalized))
        try:
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if width <= 0 or height <= 0:
                raise VideoError("The video has no readable frames")

            frames = []
            with create_landmarker(model) as landmarker:
                overlay = (
                    OverlayWriter(overlay_path, width, height)
                    if overlay_path is not None
                    else None
                )
                try:
                    while True:
                        ok, image = capture.read()
                        if not ok:
                            break
                        index = len(frames)
                        timestamp_ms = round(index * 1000 / TARGET_FPS)
                        result = detect(landmarker, image, timestamp_ms)
                        frame = frame_json(index, TARGET_FPS, result)
                        if overlay is not None:
                            draw_skeleton(
                                image, frame["landmarks"], frame["time_seconds"]
                            )
                            overlay.write(image)
                        frames.append(frame)
                finally:
                    if overlay is not None:
                        overlay.close()
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
