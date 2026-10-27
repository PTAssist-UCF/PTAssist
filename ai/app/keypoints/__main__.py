"""Command line: python -m app.keypoints VIDEO --out OUT_DIR [--model PATH].

Writes OUT_DIR/<name>.keypoints.json and OUT_DIR/<name>.overlay.mp4, then prints
the frame count, frames with a person, and the processing speed.
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from .extract import extract_keypoints
from .video import VideoError

# Relative to ai/, where the command runs. The model is not in git (see README).
DEFAULT_MODEL = Path("models/pose_landmarker_full.task")


def extract(video: Path, out_dir: Path, model: Path) -> dict[str, Any]:
    """Write the keypoint JSON and the overlay video, and return the JSON data."""
    data = extract_keypoints(video, model, out_dir / f"{video.stem}.overlay.mp4")
    json_path = out_dir / f"{video.stem}.keypoints.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")
    return data


def main() -> None:
    """Parse the arguments, check the setup, run extract(), and print a summary."""
    parser = argparse.ArgumentParser(
        prog="python -m app.keypoints",
        description="Find body keypoints in a video and draw them on a copy of it.",
    )
    parser.add_argument("video", type=Path, metavar="VIDEO", help="the input video")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        metavar="OUT_DIR",
        help="folder for the JSON and overlay",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL,
        metavar="PATH",
        help=f"MediaPipe pose model (default: {DEFAULT_MODEL})",
    )
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit("error: ffmpeg not found. Install it (see ai/README.md).")
    if not args.model.is_file():
        sys.exit(
            f"error: model file not found: {args.model}\n"
            "Download it as shown in ai/README.md (Keypoint prototype)."
        )

    args.out.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    try:
        data = extract(args.video, args.out, args.model)
    except VideoError as error:
        sys.exit(f"error: {error}")
    seconds = time.perf_counter() - start

    frames = data["frames"]
    with_person = sum(frame["landmarks"] is not None for frame in frames)
    print(f"Wrote {args.out / args.video.stem}.keypoints.json and .overlay.mp4")
    print(f"Frames: {len(frames)}, with a person: {with_person}")
    print(f"Time: {seconds:.1f} s, {len(frames) / seconds:.1f} frames per second")


if __name__ == "__main__":
    main()
