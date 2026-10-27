"""Download the pinned MediaPipe pose model for local runs and Docker builds."""

import hashlib
import urllib.request
from pathlib import Path

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_full/float16/1/pose_landmarker_full.task"
)
MODEL_SHA256 = "5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1"
MODEL_PATH = Path("models/pose_landmarker_full.task")


def main() -> None:
    """Save the model only after verifying the downloaded bytes."""
    with urllib.request.urlopen(MODEL_URL, timeout=60) as response:
        model_bytes = response.read()
    actual_hash = hashlib.sha256(model_bytes).hexdigest()
    if actual_hash != MODEL_SHA256:
        raise ValueError("The pose model download has an unexpected SHA-256")
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_bytes(model_bytes)


if __name__ == "__main__":
    main()
