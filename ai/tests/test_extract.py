"""The reusable extractor keeps frame timing and releases video resources."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import download_model
from app.keypoints import extract, video
from app.keypoints.video import VideoError
from tests.fakes import FakeFfmpeg


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


def use_fakes(
    monkeypatch: pytest.MonkeyPatch, capture: FakeCapture, ffmpeg: FakeFfmpeg
) -> None:
    """Fake normalization, decoding, the model, and the overlay's ffmpeg."""
    monkeypatch.setattr(extract, "normalize", lambda source, target: None)
    monkeypatch.setattr(extract.cv2, "VideoCapture", lambda path: capture)
    monkeypatch.setattr(extract, "create_landmarker", lambda model: FakeLandmarker())
    monkeypatch.setattr(video.subprocess, "Popen", lambda *args, **kwargs: ffmpeg)


def test_overlay_cannot_hide_an_empty_video(monkeypatch: pytest.MonkeyPatch) -> None:
    ffmpeg = FakeFfmpeg(exit_code=1)  # an overlay with no frames fails to encode
    use_fakes(monkeypatch, FakeCapture([]), ffmpeg)
    with pytest.raises(VideoError, match="no readable frames"):
        extract.extract_keypoints(Path("phone.mp4"), Path("m.task"), Path("o.mp4"))
    assert ffmpeg.killed


def test_overlay_cannot_hide_a_detection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = FakeCapture([np.zeros((480, 640, 3), dtype=np.uint8)])
    ffmpeg = FakeFfmpeg(exit_code=1)
    use_fakes(monkeypatch, capture, ffmpeg)

    def fail(*args: object) -> None:
        raise RuntimeError("pose failed")

    monkeypatch.setattr(extract, "detect", fail)
    with pytest.raises(RuntimeError, match="pose failed"):
        extract.extract_keypoints(Path("phone.mp4"), Path("m.task"), Path("o.mp4"))
    assert ffmpeg.killed and capture.released


def test_overlay_gets_every_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = FakeCapture([np.zeros((480, 640, 3), dtype=np.uint8)] * 3)
    ffmpeg = FakeFfmpeg()
    use_fakes(monkeypatch, capture, ffmpeg)
    monkeypatch.setattr(
        extract, "detect", lambda *args: SimpleNamespace(pose_landmarks=[])
    )
    data = extract.extract_keypoints(Path("phone.mp4"), Path("m.task"), Path("o.mp4"))
    assert data["video"]["frame_count"] == 3
    assert len(ffmpeg.stdin.data) == 3 * 480 * 640 * 3
    assert not ffmpeg.killed


def test_a_missing_model_fails_before_any_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalized = []
    monkeypatch.setattr(extract, "normalize", lambda *args: normalized.append(args))

    def no_model(model: Path) -> None:
        raise FileNotFoundError(model)

    monkeypatch.setattr(extract, "create_landmarker", no_model)
    with pytest.raises(FileNotFoundError):
        extract.extract_keypoints(Path("phone.mp4"), Path("missing.task"))
    assert normalized == []


def test_the_model_is_downloaded_where_the_extractor_looks() -> None:
    assert download_model.MODEL_PATH == extract.DEFAULT_MODEL
    assert extract.DEFAULT_MODEL.parent.parent == Path(download_model.__file__).parent
