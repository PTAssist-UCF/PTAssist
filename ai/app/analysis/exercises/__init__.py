"""One analyzer per exercise.

Each module has `NAME` (the exercise's name in the API), `ISSUES` (its issue
codes), and `analyze(keypoints, analyzer_version) -> AnalysisResult`, which takes
the keypoint data documented in ai/README.md and never reads video.
"""
