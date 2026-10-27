"""The reusable extractor keeps frame timing and releases video resources."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.keypoints import extract
from app.keypoints.video import VideoError


class FakeCapture:
    def __init__(self, frames: list[np.ndarray]) -> None:
        self.frames = iter(frames)
        self.released = False

    def get(self, property_id: int) -> int:
        return 640 if property_id == extract.cv2.CAP_PROP_FRAME_WIDTH else 480

    def read(self) -> tuple[bool, np.ndarray | None]:
        frame = next(self.frames, None)
        return frame is not None, frame

    def release(self) -> None:
        self.released = True


class FakeLandmarker:
    def __enter__(self) -> "FakeLandmarker":
        return self

    def __exit__(self, *args: object) -> None:
        pass


def test_extract_returns_frames_without_writing_an_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = FakeCapture([np.zeros((480, 640, 3), dtype=np.uint8)] * 2)
    timestamps = []
    monkeypatch.setattr(extract, "normalize", lambda source, target: None)
    monkeypatch.setattr(extract.cv2, "VideoCapture", lambda path: capture)
    monkeypatch.setattr(extract, "create_landmarker", lambda model: FakeLandmarker())

    def fake_detect(landmarker: FakeLandmarker, image: np.ndarray, time: int) -> object:
        timestamps.append(time)
        return SimpleNamespace(pose_landmarks=[])

    monkeypatch.setattr(extract, "detect", fake_detect)
    data = extract.extract_keypoints(Path("private-phone.mov"), Path("pose.task"))

    assert timestamps == [0, 67]
    assert data["video"] == {"width": 640, "height": 480, "fps": 15.0, "frame_count": 2}
    assert [frame["index"] for frame in data["frames"]] == [0, 1]
    assert [frame["landmarks"] for frame in data["frames"]] == [None, None]
    assert "private-phone" not in str(data)
    assert capture.released


def test_extract_releases_capture_after_detection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = FakeCapture([np.zeros((480, 640, 3), dtype=np.uint8)])
    monkeypatch.setattr(extract, "normalize", lambda source, target: None)
    monkeypatch.setattr(extract.cv2, "VideoCapture", lambda path: capture)
    monkeypatch.setattr(extract, "create_landmarker", lambda model: FakeLandmarker())

    def fail(*args: object) -> None:
        raise RuntimeError("pose failed")

    monkeypatch.setattr(extract, "detect", fail)
    with pytest.raises(RuntimeError, match="pose failed"):
        extract.extract_keypoints(Path("phone.mp4"), Path("pose.task"))
    assert capture.released


def test_extract_rejects_a_video_without_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = FakeCapture([])
    monkeypatch.setattr(extract, "normalize", lambda source, target: None)
    monkeypatch.setattr(extract.cv2, "VideoCapture", lambda path: capture)
    monkeypatch.setattr(extract, "create_landmarker", lambda model: FakeLandmarker())
    with pytest.raises(VideoError, match="no readable frames"):
        extract.extract_keypoints(Path("phone.mp4"), Path("pose.task"))
    assert capture.released
