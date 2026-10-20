"""MediaPipe Pose: find body landmarks in a frame, as plain JSON-ready data.

Names, connections, and confidence settings follow the AI team's prototype
(ptassist_squat/pose.py on the Jonathan-AI-Test branch).
"""

from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np

# MediaPipe's 33 pose landmarks, in its order.
NAMES = (
    "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner",
    "right_eye", "right_eye_outer", "left_ear", "right_ear", "mouth_left",
    "mouth_right", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky", "left_index",
    "right_index", "left_thumb", "right_thumb", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle", "left_heel",
    "right_heel", "left_foot_index", "right_foot_index",
)  # fmt: skip

# The body lines drawn on the overlay (no face or hands).
CONNECTIONS = (
    ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"), ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"), ("left_ankle", "left_heel"),
    ("left_heel", "left_foot_index"), ("left_ankle", "left_foot_index"),
    ("right_shoulder", "right_hip"), ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"), ("right_ankle", "right_heel"),
    ("right_heel", "right_foot_index"), ("right_ankle", "right_foot_index"),
    ("left_shoulder", "right_shoulder"), ("left_hip", "right_hip"),
)  # fmt: skip
JOINTS = sorted({name for pair in CONNECTIONS for name in pair})

# One frame's landmarks: name -> [x, y, visibility, presence].
Landmarks = dict[str, list[float]]


def create_landmarker(model_path: Path) -> mp.tasks.vision.PoseLandmarker:
    """A MediaPipe PoseLandmarker for one video. Close it when done."""
    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return mp.tasks.vision.PoseLandmarker.create_from_options(options)


def detect(
    landmarker: mp.tasks.vision.PoseLandmarker, image: np.ndarray, timestamp_ms: int
) -> mp.tasks.vision.PoseLandmarkerResult:
    """Run the landmarker on one BGR frame. Timestamps must strictly increase."""
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return landmarker.detect_for_video(
        mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp_ms
    )


def _score(value: float | None) -> float:
    # MediaPipe can leave a score empty. Treat that as no confidence.
    return 0.0 if value is None else round(float(value), 3)


def frame_json(
    index: int, fps: float, result: mp.tasks.vision.PoseLandmarkerResult
) -> dict[str, Any]:
    """One entry of the JSON "frames" list, from a MediaPipe pose result.

    x and y are normalized image coordinates, rounded to 4 decimals. landmarks is
    None when no person was found.
    """
    landmarks = None
    if result.pose_landmarks:
        landmarks = {
            name: [
                round(float(point.x), 4),
                round(float(point.y), 4),
                _score(point.visibility),
                _score(point.presence),
            ]
            for name, point in zip(NAMES, result.pose_landmarks[0], strict=True)
        }
    return {
        "index": index,
        "time_seconds": round(index / fps, 3),
        "landmarks": landmarks,
    }


def draw_skeleton(
    image: np.ndarray,
    landmarks: Landmarks | None,
    time_seconds: float,
    min_confidence: float = 0.5,
) -> None:
    """Draw body lines, joint dots, and the time on a BGR frame, in place.

    Skips joints whose visibility or presence is below min_confidence, and joints
    outside the image.
    """
    height, width = image.shape[:2]
    points = {}
    for name, (x, y, visibility, presence) in (landmarks or {}).items():
        if min(visibility, presence) >= min_confidence and 0 <= x <= 1 and 0 <= y <= 1:
            points[name] = (round(x * width), round(y * height))

    for start, end in CONNECTIONS:
        if start in points and end in points:
            cv2.line(image, points[start], points[end], (70, 220, 70), 2, cv2.LINE_AA)
    for name in JOINTS:
        if name in points:
            cv2.circle(image, points[name], 4, (0, 220, 255), -1, cv2.LINE_AA)

    text = f"{time_seconds:.2f} s"
    for color, thickness in (((0, 0, 0), 4), ((255, 255, 255), 2)):  # outlined
        cv2.putText(
            image, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, thickness
        )
