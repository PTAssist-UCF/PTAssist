"""Live-feedback readiness (SCRUM-91): squat analysis on frames fed one at a time.

Live feedback (a Spring goal) will get keypoint frames from a camera one by one, with
no video file and no keypoint module. These tests pass synthetic keypoint JSON frames
to `SquatAnalyzer.update` one at a time, as a live caller would, and compare what it
counts with `analyze_squat` on the whole clip.
"""

import itertools
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from app.analysis.exercises.squat import FrameResult, SquatAnalyzer, analyze_squat
from app.analysis.landmarks import Landmark
from tests.test_squat import FPS, SIZE, pose, squat_angles

AI_DIR = Path(__file__).resolve().parents[1]
VERSION = "test"

# One frame's landmarks as in the keypoint JSON: name -> [x, y, visibility, presence].
Landmarks = dict[str, list[float]]


def json_pose(
    knee_angle: float, lean: float = 10.0, *, left: float = 0.95, right: float = 0.95
) -> Landmarks:
    """test_squat's side-on pose as keypoint JSON, with each side's visibility."""
    visibility = {"left": left, "right": right}
    landmarks: Landmarks = {}
    for name, lm in pose(knee_angle, lean).items():
        score = visibility.get(name.split("_")[0], lm.visibility)  # nose: unchanged
        landmarks[name] = [lm.x, lm.y, score, lm.presence]
    return landmarks


def standing(frames: int = 8, **visibility: float) -> list[Landmarks | None]:
    """Standing still, knees straight."""
    return [json_pose(175, **visibility) for _ in range(frames)]


def squat(
    bottom: float = 90,
    seconds: float = 3,
    lean: float = 10.0,
    gap: Sequence[Landmarks | None] = (),
    **visibility: float,
) -> list[Landmarks | None]:
    """One squat down to `bottom` degrees and up again, then standing still.

    `gap` frames go in at the bottom, where the near leg is hardest to see.
    """
    frames: list[Landmarks | None] = [
        json_pose(angle, lean, **visibility)
        for angle, _ in squat_angles(bottom, seconds)
    ]
    middle = len(frames) // 2
    frames[middle:middle] = gap
    return frames + standing(**visibility)


def nobody(frames: int) -> list[Landmarks | None]:
    """Frames in which MediaPipe found no person."""
    return [None] * frames


def poorly_seen(frames: int) -> list[Landmarks | None]:
    """A person at the bottom of a squat whose joints score below the 0.65 limit."""
    return [json_pose(90, left=0.4, right=0.4) for _ in range(frames)]


def clip(*parts: list[Landmarks | None]) -> dict[str, Any]:
    """Keypoint JSON for a whole clip (format in ai/README.md), at 15 fps."""
    frames = [
        {"index": index, "time_seconds": round(index / FPS, 3), "landmarks": landmarks}
        for index, landmarks in enumerate(itertools.chain(*parts))
    ]
    return {
        "video": {
            "width": SIZE,
            "height": SIZE,
            "fps": float(FPS),
            "frame_count": len(frames),
        },
        "model": "pose_landmarker_full.task",
        "frames": frames,
    }


# Each clip, and the number of full reps it holds.
CLIPS = {
    # A full set: a clean rep, then one rep for each form issue, then a clean rep.
    "full-set": (
        clip(
            standing(),
            squat(),
            squat(125),  # not deep enough
            squat(lean=55),  # leaning forward
            squat(seconds=1.2),  # too fast
            squat(),
        ),
        5,
    ),
    # Tracking lost at the bottom for about 0.5 s keeps the rep; over 0.75 s drops it.
    "tracking-lost": (
        clip(
            standing(),
            squat(),
            squat(gap=nobody(3) + poorly_seen(4)),  # still a rep
            squat(gap=nobody(15)),  # dropped
            squat(gap=poorly_seen(15)),  # dropped
            squat(),
        ),
        3,
    ),
    # A dip to 150 degrees is not a rep, and the clip stops at the bottom of a squat.
    "ends-mid-rep": (
        clip(standing(), squat(), squat(150), squat(), squat()[:25]),
        2,
    ),
    # The patient turns around between reps, so the near side changes. The far side
    # is partly hidden, and its scores (0.5) are too low to measure it.
    "turns-around": (
        clip(
            standing(right=0.5),
            squat(right=0.5),
            squat(right=0.5),
            standing(left=0.5),
            squat(left=0.5),
            squat(left=0.5),
        ),
        4,
    ),
}


def feed_frame(
    analyzer: SquatAnalyzer, frame: dict[str, Any], video: dict[str, Any]
) -> FrameResult:
    """Pass one keypoint JSON frame to the analyzer, as a live caller would."""
    found = frame["landmarks"]
    landmarks = (
        None
        if found is None
        else {name: Landmark(*values) for name, values in found.items()}
    )
    return analyzer.update(
        landmarks, frame["time_seconds"], video["width"], video["height"]
    )


@pytest.mark.parametrize("name", CLIPS)
def test_frames_one_at_a_time_give_the_same_rep_count_as_the_whole_clip(
    name: str,
) -> None:
    keypoints, full_reps = CLIPS[name]
    whole = analyze_squat(keypoints).result(VERSION)

    live = SquatAnalyzer()
    counts = []
    for frame in keypoints["frames"]:
        counts.append(feed_frame(live, frame, keypoints["video"]).rep_count)
        # Never ahead of the whole clip and never behind it: a rep counts on the
        # frame where it ends, and a counted rep never changes after that.
        ended = [rep for rep in whole.reps if rep.end_seconds <= frame["time_seconds"]]
        assert live.result(VERSION).reps == ended

    assert counts[-1] == whole.rep_count == full_reps
    assert counts == sorted(counts)  # the running count never goes down
    assert live.result(VERSION) == whole  # same reps, times, scores, and feedback


def test_a_clip_cut_at_any_frame_gives_the_live_result_so_far() -> None:
    # Neither needs a later frame or the end of the clip, so analyzing the clip up to
    # any frame gives what the live analyzer has after that frame.
    keypoints, _ = CLIPS["ends-mid-rep"]
    live = SquatAnalyzer()
    for count, frame in enumerate(keypoints["frames"], start=1):
        feed_frame(live, frame, keypoints["video"])
        cut = {
            **keypoints,
            "video": {**keypoints["video"], "frame_count": count},
            "frames": keypoints["frames"][:count],
        }
        assert analyze_squat(cut).result(VERSION) == live.result(VERSION)


def test_reset_starts_a_new_set_with_the_same_analyzer() -> None:
    first, _ = CLIPS["full-set"]
    second, _ = CLIPS["ends-mid-rep"]
    live = SquatAnalyzer()
    for frame in first["frames"]:
        feed_frame(live, frame, first["video"])
    live.reset()  # the second set's timestamps start again at 0
    for frame in second["frames"]:
        feed_frame(live, frame, second["video"])
    assert live.result(VERSION) == analyze_squat(second).result(VERSION)


# Runs in a new Python process, so modules that other tests imported do not count.
# It imports every analysis module, then feeds the clip from stdin frame by frame.
LIVE_RUN = """
import importlib, json, pkgutil, sys

sys.path.insert(0, sys.argv[1])
import app.analysis
from app.analysis.exercises.squat import SquatAnalyzer
from app.analysis.landmarks import Landmark

for module in pkgutil.walk_packages(app.analysis.__path__, "app.analysis."):
    importlib.import_module(module.name)
keypoints = json.load(sys.stdin)
width, height = keypoints["video"]["width"], keypoints["video"]["height"]
analyzer = SquatAnalyzer()
for frame in keypoints["frames"]:
    found = frame["landmarks"]
    landmarks = None if found is None else {n: Landmark(*v) for n, v in found.items()}
    analyzer.update(landmarks, frame["time_seconds"], width, height)
print(json.dumps({"rep_count": analyzer.rep_count, "modules": sorted(sys.modules)}))
"""
VIDEO_MODULES = ("app.keypoints", "cv2", "mediapipe")


def test_live_analysis_loads_no_keypoint_or_video_code() -> None:
    keypoints, full_reps = CLIPS["tracking-lost"]
    run = subprocess.run(
        [sys.executable, "-c", LIVE_RUN, str(AI_DIR)],
        input=json.dumps(keypoints),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stderr
    output = json.loads(run.stdout)
    assert output["rep_count"] == full_reps
    # A module counts if it is one of VIDEO_MODULES or inside one of them.
    video = tuple(f"{name}." for name in VIDEO_MODULES)
    loaded = [name for name in output["modules"] if f"{name}.".startswith(video)]
    assert loaded == []
