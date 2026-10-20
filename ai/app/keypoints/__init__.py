"""Video to body keypoints: normalize a video with ffmpeg, then run MediaPipe Pose.

Prototype for SCRUM-27. Run it from the ai/ folder:

    python -m app.keypoints VIDEO --out OUT_DIR [--model PATH]

It writes OUT_DIR/<name>.keypoints.json (landmarks for every frame) and
OUT_DIR/<name>.overlay.mp4 (the skeleton drawn on the video). See ai/README.md.
"""
