"""Keypoint module checks that need neither ffmpeg nor the MediaPipe model file."""

import errno
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.analysis.landmarks import Landmark
from app.analysis_contract import MAX_VIDEO_SECONDS
from app.keypoints import video
from app.keypoints.pose import NAMES, draw_skeleton, frame_json
from app.keypoints.video import (
    OverlayError,
    VideoError,
    VideoTimeoutError,
    normalize_command,
    overlay_command,
)
from tests.fakes import FakeFfmpeg


def test_normalize_command_drops_audio_and_sets_rate_and_size() -> None:
    args = normalize_command(Path("in.mov"), Path("out.mp4"))
    assert args[0] == "ffmpeg"
    # Rotation is on by default; ffmpeg 6.1 and older would read -i as its value.
    assert "-autorotate" not in args
    assert args[args.index("-i") + 1] == "in.mov"
    assert args[args.index("-map") + 1] == "0:v:0"  # first video stream, no audio
    # An output option (after -i): stop just past the longest video we analyze.
    assert args.index("-t") > args.index("-i")
    assert args[args.index("-t") + 1] == str(MAX_VIDEO_SECONDS + 1)
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


def test_normalization_failure_logs_the_reason_without_the_video_path(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    source = Path("videos/patient-name.mov")
    stderr = f"\n{source}: Invalid data found when processing input\n\n"
    decoding = []

    def failed_ffmpeg(*args: object, **kwargs: object) -> SimpleNamespace:
        decoding.append(kwargs.get("errors"))
        return SimpleNamespace(returncode=1, stderr=stderr)

    monkeypatch.setattr(video.subprocess, "run", failed_ffmpeg)
    with pytest.raises(VideoError, match="could not read the input video") as error:
        video.normalize(source, Path("normalized.mp4"))
    assert "patient-name" not in str(error.value)
    assert "<input>: Invalid data found when processing input" in caplog.text
    assert "patient-name" not in caplog.text
    # Bytes the locale cannot decode must not crash the failure report.
    assert decoding == ["replace"]


def test_redaction_leaves_words_that_match_a_short_file_name() -> None:
    source = Path("video")  # the name POST /analyze gives its downloaded copy
    line = video._last_error_line(f"{source}: no video stream found\n", source)
    assert line == "<input>: no video stream found"
    quoted = video._last_error_line(f"Could not open '{source}'.", source)
    assert quoted == "Could not open <input>."


def test_redaction_covers_the_ffmpeg_7_input_file_line() -> None:
    # The exact form ffmpeg 7.1 prints (checked by hand), with a non-ASCII name.
    source = Path("José_Müller_squat.mov")
    line = video._last_error_line(f"Error opening input file {source}.\n", source)
    assert line == "Error opening input file <input>."
    assert video._last_error_line("", source) == "no details"


def test_normalization_timeout_is_not_a_video_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeouts = []

    def slow_ffmpeg(command: list[str], **kwargs: object) -> None:
        timeouts.append(kwargs["timeout"])
        raise subprocess.TimeoutExpired(command, video.NORMALIZE_TIMEOUT_SECONDS)

    monkeypatch.setattr(video.subprocess, "run", slow_ffmpeg)
    with pytest.raises(VideoTimeoutError, match="took too long") as error:
        video.normalize(Path("patient-name.mov"), Path("normalized.mp4"))
    # A slow server is not a bad video: callers must not report video_unreadable,
    # and an `except OSError` for file problems must not catch it either.
    assert not isinstance(error.value, VideoError | OSError)
    assert timeouts == [video.NORMALIZE_TIMEOUT_SECONDS]
    assert "patient-name" not in str(error.value)
    assert error.value.__suppress_context__  # the command is not chained into logs


@pytest.mark.parametrize(
    "close_error",
    [
        None,
        BrokenPipeError(errno.EPIPE, "Broken pipe"),  # Linux, ffmpeg already exited
        OSError(errno.EINVAL, "Invalid argument"),  # Windows, ffmpeg already exited
    ],
)
def test_overlay_writer_reports_an_ffmpeg_failure_as_an_overlay_error(
    monkeypatch: pytest.MonkeyPatch, close_error: OSError | None
) -> None:
    process = FakeFfmpeg(exit_code=1, close_error=close_error)
    monkeypatch.setattr(video.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(OverlayError, match="overlay") as error:
        with video.OverlayWriter(Path("overlay.mp4"), 2, 2) as overlay:
            overlay.write(np.zeros((2, 2, 3), dtype=np.uint8))
    assert not isinstance(error.value, VideoError)
    assert process.stdin.closed and not process.killed


def test_overlay_writer_stops_quietly_and_keeps_the_original_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = FakeFfmpeg(exit_code=1)  # would fail if it were finished normally
    monkeypatch.setattr(video.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(ZeroDivisionError):
        with video.OverlayWriter(Path("overlay.mp4"), 2, 2):
            raise ZeroDivisionError
    assert process.killed and process.stdin.closed


@pytest.mark.parametrize(
    "write_error",
    [
        BrokenPipeError(errno.EPIPE, "Broken pipe"),
        OSError(errno.EINVAL, "Invalid argument"),
    ],
)
def test_overlay_writer_reports_a_closed_pipe_as_an_overlay_error(
    monkeypatch: pytest.MonkeyPatch, write_error: OSError
) -> None:
    process = FakeFfmpeg(exit_code=1)
    monkeypatch.setattr(video.subprocess, "Popen", lambda *args, **kwargs: process)

    def fail_write(data: bytes) -> None:
        raise write_error

    monkeypatch.setattr(process.stdin, "write", fail_write)
    with pytest.raises(OverlayError, match="overlay"):
        with video.OverlayWriter(Path("overlay.mp4"), 2, 2) as overlay:
            overlay.write(np.zeros((2, 2, 3), dtype=np.uint8))
    assert process.killed and process.stdin.closed


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
