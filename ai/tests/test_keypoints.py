"""Keypoint prototype checks that need neither ffmpeg nor the MediaPipe model file."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.analysis.landmarks import Landmark
from app.keypoints import video
from app.keypoints.pose import NAMES, draw_skeleton, frame_json
from app.keypoints.video import VideoError, normalize_command, overlay_command


def test_normalize_command_drops_audio_and_sets_rate_and_size() -> None:
    args = normalize_command(Path("in.mov"), Path("out.mp4"))
    assert args[0] == "ffmpeg"
    assert args.index("-autorotate") < args.index("-i")
    assert args[args.index("-i") + 1] == "in.mov"
    assert args[args.index("-map") + 1] == "0:v:0"  # first video stream, no audio
    filters = args[args.index("-vf") + 1]
    assert filters.startswith("fps=15,")
    assert "min(1280,iw)" in filters and "min(1280,ih)" in filters
    assert "force_divisible_by=2" in filters
    assert args[-3:] == ["-pix_fmt", "yuv420p", "out.mp4"]


def test_overlay_command_reads_raw_frames_of_the_given_size() -> None:
    args = overlay_command(Path("overlay.mp4"), 640, 360)
    assert args[args.index("-s") + 1] == "640x360"
    assert args[args.index("-r") + 1] == "15"
    assert args[args.index("-i") + 1] == "-"
    assert args[args.index("-c:v") + 1] == "libx264"
    assert args[-1] == "overlay.mp4"


def test_normalization_failure_does_not_reveal_a_video_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed_ffmpeg(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stderr="Failed to open patient-name.mov")

    monkeypatch.setattr(video.subprocess, "run", failed_ffmpeg)
    with pytest.raises(VideoError, match="could not read the input video") as error:
        video.normalize(Path("patient-name.mov"), Path("normalized.mp4"))
    assert "patient-name" not in str(error.value)


def test_frame_json_rounds_scores_and_maps_missing_scores_to_zero() -> None:
    point = SimpleNamespace(x=0.123456, y=-0.012345, visibility=0.98765, presence=None)
    result = SimpleNamespace(pose_landmarks=[[point] * len(NAMES)])

    frame = frame_json(1, 15, result)

    assert frame["index"] == 1
    assert frame["time_seconds"] == 0.067
    assert tuple(frame["landmarks"]) == NAMES
    assert frame["landmarks"]["left_knee"] == [0.1235, -0.0123, 0.988, 0.0]
    assert Landmark(*frame["landmarks"]["left_knee"]).confidence == 0.0
    json.dumps(frame)  # Plain types only.


def test_frame_json_without_a_person_has_null_landmarks() -> None:
    frame = frame_json(0, 15, SimpleNamespace(pose_landmarks=[]))
    assert frame == {"index": 0, "time_seconds": 0.0, "landmarks": None}


def test_draw_skeleton_skips_low_confidence_and_out_of_image_joints() -> None:
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    landmarks = {
        "left_shoulder": [0.25, 0.5, 0.9, 0.9],  # pixel (50, 100)
        "left_elbow": [0.75, 0.5, 0.9, 0.9],  # pixel (150, 100)
        "right_shoulder": [0.5, 0.9, 0.9, 0.3],  # low presence
        "left_hip": [0.5, 0.7, 0.9, 0.9],  # pixel (100, 140)
        "right_hip": [1.2, 0.7, 0.9, 0.9],  # outside the image
    }

    draw_skeleton(image, landmarks, 1.5)

    assert image[100, 50].any()  # left_shoulder dot
    assert image[100, 100].any()  # left_shoulder to left_elbow line
    assert not image[180, 100].any()  # right_shoulder is not drawn
    assert not image[140, 160].any()  # no line toward right_hip
    assert image[10:35, 10:90].any()  # the time, top left
