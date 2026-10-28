# AI service

Python service that turns an exercise video into a rep count (or a hold time), a form score, and feedback. It is internal only: the backend is the only caller, and it cannot be reached from the internet.

## Stack

FastAPI, OpenCV, ffmpeg, MediaPipe Pose, pytest, ruff. Runtime dependencies in `requirements.txt`; test and lint tools in `requirements-dev.txt`. MediaPipe, OpenCV, and NumPy are pinned to the same versions as the AI team's prototype.

## Layout

```
app/
  main.py               The web server: GET /health and POST /analyze
  analysis_contract.py  The request and result shared with the backend (exact copy there)
  schemas.py            Shapes used only here (the GET /health response)
  keypoints/            Video to body keypoints, with a reusable extractor and CLI
    video.py            ffmpeg: normalize the input video, write the overlay video
    pose.py             MediaPipe landmarks as JSON-ready data, and the skeleton drawing
    extract.py          Reusable video-to-keypoints function
    __main__.py         The command line: python -m app.keypoints
  analysis/             Shared geometry, smoothing, visibility, and result framework
    landmarks.py        Plain normalized image landmarks
    geometry.py         Angles, distances, midpoints, and signed line offsets
    smoothing.py        Time-based exponential smoothing with tracking-gap reset
    visibility.py       Required-joint checks and a mask preserving frame indices
    exercises/          One file per exercise
tests/                  pytest tests. fixtures/ holds keypoint JSON test data
Dockerfile              The service image: Python, ffmpeg, OpenCV, MediaPipe
```

## Run locally

Needs Python 3.12. Run these from `ai/`:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

uvicorn app.main:app --reload --port 8001   # http://localhost:8001/health and /docs
pytest
ruff check .
ruff format --check .
```

On Windows, if PowerShell says running scripts is disabled, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.

The service uses port 8001, so it can run next to the API on 8000. The API finds it through `AI_SERVICE_URL` in `/.env.example`. It needs no environment variables yet.

`/docs` is FastAPI's built-in page for trying the endpoints: open `POST /analyze`, click **Try it out**, and send a request.

pip installs OpenCV and MediaPipe but not ffmpeg, which is a separate program. The Docker image has it. To use it outside Docker, install it from https://ffmpeg.org/download.html.

## Docker

```bash
docker build -t ptassist-ai ai              # from the repo root
docker run --rm -p 8001:8001 ptassist-ai    # http://localhost:8001/health
```

The image starts from `python:3.12-slim-trixie` (Debian 13), installs ffmpeg and the system libraries OpenCV and MediaPipe need with `apt-get`, then installs `requirements.txt` with pip. It runs as a non-root user. The `Dockerfile` explains each step.
The image also downloads the fixed Pose Landmarker Full model and checks its SHA-256 during the build. Local runs download it separately (see Download the model, under Pipeline).

### In Docker Compose

`/compose.yaml` runs this image as the `ai` service, on port 8001 (see the root README, Getting started). After you change the code, rebuild it with `docker compose up --build`.

- Other containers reach it at `http://ai:8001`, which is the API's `AI_SERVICE_URL` in Compose.
- Its health check calls `/health` with Python, because the image has no `curl`.
- In Compose, video read links start with `http://azurite:10000/`, which this container can open (see `backend/README.md`, Storage in Docker Compose).

## Pipeline

```
video -> normalize (ffmpeg) -> keypoints (MediaPipe) -> analysis (rules per exercise) -> result
```

| Step | Module | Does |
| --- | --- | --- |
| Normalize | `app/keypoints/` | Fix rotation, frame rate, and size |
| Keypoints | `app/keypoints/` | Body landmarks for each frame |
| Analysis | `app/analysis/` | Shared logic: joint angles, smoothing, rep splitting, scoring |
| Exercise rules | `app/analysis/exercises/` | One file per exercise: what counts as a rep, form checks, feedback |

**Keep keypoints and analysis separate.** Analysis takes keypoint frames, never video. That lets live feedback (a Spring goal) reuse the same analysis code on frames from a camera.

### Keypoint module (SCRUM-49)

`app.keypoints.extract.extract_keypoints(video, model)` returns the documented keypoint data in memory. It normalizes phone video with ffmpeg, applies rotation metadata, decodes the normalized frames with OpenCV, and runs MediaPipe. Passing `overlay_path` additionally writes a debug overlay. Temporary video files are deleted when the call ends. `POST /analyze` does not call it yet; that integration belongs to SCRUM-52. The command-line tool uses the same function and saves its return value as JSON.

The unit tests check frame timing, cleanup, and the ffmpeg settings. A local iPhone check on October 27, 2026 used a 34.64-second portrait `.MOV` (H.264, 1080 x 1920, about 30 fps). It normalized to 720 x 1280 at 15 fps, with 520 frames. MediaPipe found a person in 497 frames; the missing detections were before and after the exercise movements. Both arms' required joints passed the exercise's confidence and framing checks in all 382 frames spanning the movements.

Synthetic HEVC `.mov` and rotation-metadata checks also passed. Videos are never committed here.

**Download the model.** It uses MediaPipe's Pose Landmarker Full model (about 9 MB). Model files are not kept in git (`*.task` is in `/.gitignore`). From `ai/`, run `python download_model.py`. The script verifies the SHA-256 before saving the file. A manual alternative is:

```bash
curl -fL --create-dirs -o models/pose_landmarker_full.task https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task
sha256sum models/pose_landmarker_full.task   # Windows PowerShell: Get-FileHash models\pose_landmarker_full.task
```

In Windows PowerShell, type `curl.exe` instead of `curl`. The SHA-256 must be `5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1` (`Get-FileHash` prints it in capitals).

**Run it** from `ai/`. It needs ffmpeg (see [Run locally](#run-locally)).

```bash
python -m app.keypoints path/to/video.mov --out path/to/output-folder
```

`--model PATH` uses a model file somewhere else (the default is `models/pose_landmarker_full.task`). Use an output folder outside the repo: git ignores the overlay video but not the JSON. It writes two files named after the video:

| File | Holds |
| --- | --- |
| `<name>.keypoints.json` | Body landmarks for every frame (format below) |
| `<name>.overlay.mp4` | The normalized video with the skeleton drawn on it (green lines, yellow dots) and the time in seconds, top left. Joints with a confidence below 0.5, or outside the image, are not drawn. H.264, so it plays in browsers and in Windows |

Then it prints the frame count, the frames with a person, and the speed of the whole run, model loading included:

```
Wrote path/to/output-folder/video.keypoints.json and .overlay.mp4
Frames: 63, with a person: 63
Time: 3.2 s, 19.6 frames per second
```

MediaPipe also prints a few `INFO` and `W0000` lines when it starts. They are harmless. On Linux outside Docker, MediaPipe needs `libegl1` and `libgles2` (`sudo apt-get install libegl1 libgles2`); without them it fails with `libEGL.so.1: cannot open shared object file`. The Docker image has them.

If ffmpeg or the model file is missing, or ffmpeg cannot read the video, it prints an `error:` line and exits with code 1.

**Normalization.** ffmpeg first turns every input into an upright H.264 MP4, in a temporary folder that is deleted at the end. The constants are at the top of `app/keypoints/video.py`.

| Setting | Value | Why |
| --- | --- | --- |
| Rotation | Applied | Phones store portrait video sideways with a rotation tag. ffmpeg applies the tag when it re-encodes, so the output is upright |
| Frame rate | Constant 15 fps (`TARGET_FPS`) | PT reps take 2 seconds or more, so 15 is plenty, and it halves MediaPipe's time compared with 30 |
| Size | Longer side at most 1280 px (`MAX_SIDE_PIXELS`) | MediaPipe shrinks every image internally, so bigger frames only cost time. Never scaled up; width and height are even. Assumes square pixels, which phone videos always have |
| Streams | First video stream only | Audio is dropped |

MediaPipe then runs on each frame: the Tasks API `PoseLandmarker` in video mode, one person, and detection, presence, and tracking confidence 0.5, like the prototype on `Jonathan-AI-Test`. Frame timestamps are `round(index * 1000 / 15)` milliseconds.

**Keypoint JSON.** One object per video (shortened here: each `landmarks` has all 33 names):

```json
{
  "video": {"width": 1280, "height": 720, "fps": 15.0, "frame_count": 63},
  "model": "pose_landmarker_full.task",
  "frames": [
    {"index": 0, "time_seconds": 0.0, "landmarks": {"nose": [0.5722, 0.1251, 1.0, 1.0], "left_eye_inner": [0.5783, 0.1156, 1.0, 1.0]}},
    {"index": 1, "time_seconds": 0.067, "landmarks": null}
  ]
}
```

| Field | Meaning |
| --- | --- |
| `video.width`, `video.height` | Size of the normalized video in pixels. Pass these to the geometry helpers |
| `video.fps` | Always 15.0 |
| `video.frame_count` | The number of entries in `frames` |
| `model` | The MediaPipe model file |
| `frames[].index` | Frame number, from 0. Frames without a person are kept, so there are no gaps |
| `frames[].time_seconds` | `index / fps`, rounded to 3 decimals |
| `frames[].landmarks` | MediaPipe's 33 landmarks by name (`NAMES` in `app/keypoints/pose.py`), or `null` when no person was found |

Each landmark is `[x, y, visibility, presence]`:

- `x` and `y` are normalized image coordinates: 0 to 1 across the width and height, rounded to 4 decimals. They can be slightly below 0 or above 1 when MediaPipe guesses a joint outside the frame.
- `visibility` and `presence` are 0 to 1, rounded to 3 decimals. A missing score becomes 0.
- The order matches `Landmark`, so `Landmark(*values)` (from `app/analysis/landmarks.py`) turns one into input for the analysis helpers.
- There is no `z` and there are no world (3D) landmarks. MediaPipe has both, so they can be added later as new fields.
- The JSON leaves out the input file's path, which could hold a patient's name.

`tests/test_keypoints.py` checks the ffmpeg arguments, the JSON conversion, and the drawing. It needs neither ffmpeg nor the model, so CI runs it without them. The prototype was also checked by hand on a 4-second dance clip (a Pexels video, as used in the `tensorflow/tfjs-models` demos; not in the repo) and on variants of it made with ffmpeg: 1920x1080 at 30 fps with audio (came out 1280x720 at 15 fps, no audio), a portrait clip stored sideways with a rotation tag (came out upright, 720x1280), and HEVC in a `.mov`. Every overlay followed the joints.

### Shared analyzer helpers (SCRUM-30 and SCRUM-50)

The helpers in `app/analysis/` use plain Python data and have no camera, OpenCV,
or MediaPipe imports. They follow the geometry and confidence conventions in
the AI team's `ptassist_squat` proof of concept on `Jonathan-AI-Test`.

- `Landmark(x, y, visibility=1.0, presence=1.0)` holds normalized image
  coordinates. `confidence` is the lower of visibility and presence. The future
  keypoint adapter should supply both scores from the pose provider; missing
  provider scores should be mapped to zero rather than using these defaults.
- `joint_angle(a, joint, b, width, height)` returns the angle at `joint` in
  degrees from 0 to 180. `lean_from_vertical(shoulder, hip, width, height)`
  returns unsigned lean from 0 to 90 degrees. Both scale normalized coordinates
  by the actual frame dimensions, so a non-square image does not distort angles.
  These are 2D image-plane measurements, not 3D joint angles. Nonfinite
  coordinates, invalid dimensions, and coincident points raise `ValueError`.
- `distance(a, b, width, height)` returns the distance between two landmarks in
  pixels (zero for coincident points). Pass `reference_length_pixels=...` to
  divide it by a positive finite torso or limb length, measured using the same
  image dimensions. For example, compute torso length with `distance(shoulder,
  hip, width, height)`, then use that length to normalize wrist displacement.
- `midpoint(a, b)` returns a `Landmark` at the normalized midpoint, suitable for
  the other helpers. Its visibility and presence are the lower of the input
  scores, so averaging two joints cannot improve confidence. Invalid coordinates
  or confidence scores raise `ValueError`. It needs no frame dimensions because
  midpoint averaging commutes with image scaling.
- `signed_segment_angle(a, b, c, d, width, height)` returns the rotation from
  directed segment `a -> b` to `c -> d` in degrees from -180 to 180. With image
  coordinates (y increases downward), positive means clockwise. Reversing the
  segment order reverses the sign, except that opposite segments lie at the
  ambiguous +/-180 boundary. Coincident endpoints raise `ValueError`.
- `signed_distance_to_line(landmark, line_start, line_end, width, height)` returns
  perpendicular distance in pixels to the **infinite line** through the two
  endpoints, including when the projection lies beyond the segment. For a line
  pointing right, points below it have positive distance; reversing endpoints
  reverses the sign. It also accepts `reference_length_pixels` for normalization.
  Coincident line endpoints raise `ValueError`. An analyzer must use a consistent
  endpoint order when interpreting the sign, including when a patient faces the
  opposite direction in a side view.
- `is_frame_visible(landmarks, required_joints, ...)` requires every named joint
  to be present, within the image margin, and to have both visibility and presence
  at least `min_confidence`. Invalid scores and coordinates are rejected. The
  prototype defaults are `min_confidence=0.65` and `frame_margin=0.025`; each
  analyzer can override them. Only the exercise's required joints are checked.
  `visibility_mask(frames, required_joints, ...)` returns one Boolean per frame.
  Keep the original timestamps and indices; do not close tracking gaps by
  dropping rejected frames and renumbering the remainder.
- `ExponentialSmoother(tau_seconds=0.12, max_gap_seconds=0.75)` smooths one scalar
  signal with `alpha = 1 - exp(-elapsed_seconds / tau_seconds)`. Create one per
  measurement. The first sample passes through; `None` marks a rejected frame
  and returns `None`. History survives short gaps, but a gap **longer than** the
  limit resets the signal to the next valid sample. Values must be finite and
  timestamps must be nonnegative, finite, and strictly increasing. Call `reset()`
  for a new clip or when switching the tracked side.

For example, after converting a pose into a dictionary of `Landmark` objects:

```python
from app.analysis.geometry import joint_angle
from app.analysis.smoothing import ExponentialSmoother
from app.analysis.visibility import is_frame_visible

knee_smoother = ExponentialSmoother()  # Keep this instance across the clip.
required = ("left_hip", "left_knee", "left_ankle")


def knee_measurement(landmarks, timestamp_seconds, width, height):
    angle = None
    if is_frame_visible(landmarks, required):
        try:
            angle = joint_angle(*(landmarks[name] for name in required), width, height)
        except ValueError:
            pass  # Degenerate geometry is another rejected measurement.
    return knee_smoother.update(angle, timestamp_seconds)
```

An analyzer must abstain from rep and form decisions when this returns `None`.
Synthetic tests in `tests/test_geometry.py`, `tests/test_smoothing.py`, and
`tests/test_visibility.py` are collected by the existing `AI tests` PR CI job.
These helpers do not change the stub endpoint's results or the shared API contract.

`app.analysis.framework` turns exercise measurements into result objects without
reading video. `RepSplitter(start_threshold, count_threshold, rest_threshold,
direction)` waits for the start position, counts only a movement that crosses the
count threshold and returns to rest, and discards a movement after more than 0.75
seconds without a valid measurement. Pass each smoothed measurement and its video
timestamp to `update`; a completed movement returns a `RepWindow`.

An exercise analyzer reports `RepObservation` entries with issue codes, timestamps,
side, and metrics. `build_rep_result` subtracts each issue's penalty once, floors
the rep score at zero, averages rep scores, and chooses up to three feedback tips.
For a hold, report `HoldObservation` entries with good-form seconds and use
`build_hold_result`; it scores each hold by its good-form share and weights the
overall score by hold duration. Issue messages, tips, and penalties come from
`IssueDefinition`. Scores round exact halves up. The empty and issue-free
feedback lines match `docs/analysis-result.md`. `tests/test_framework.py` uses a
placeholder analyzer to check the resulting contract.

## API

The service has no sign-in: it is internal only, and the backend is its only caller.

The request and result of `POST /analyze` are the Pydantic models in `app/analysis_contract.py`, the contract between this service and the backend. [`docs/analysis-result.md`](../docs/analysis-result.md) explains every field, the error codes, scoring, and feedback, with example results in `docs/analysis-result-examples/`.

**The backend keeps an exact copy of that file** in `backend/app/schemas/analysis_contract.py`. Edit only the copy in `ai/`, then copy it over from the repo root:

```bash
cp ai/app/analysis_contract.py backend/app/schemas/analysis_contract.py
```

A test in each service fails if the two files differ, and a pull request cannot merge until they match. Results are saved and kept, so only add fields (with a default value). Do not rename or remove a field, or change its type; if that is ever unavoidable, see [Changing the contract](../docs/analysis-result.md#changing-the-contract).

### `GET /health`

Returns `{"status": "ok"}` while the server is up. Docker and Azure use it to check the service.

### `POST /analyze`

**For now this is a stub:** it ignores the video and returns a made-up result in the real shape. For `plank` it returns a hold result, for the other four exercises the same result with 3 reps and no sides (`side` is null; see `side-leg-raise.json` for reps with sides), and for any other name a failed result with `unknown_exercise`. The real pipeline replaces it in Sprint 2.

Request (`session_id` is the backend's session id, a UUID):

```json
{
  "session_id": "3f6c1a52-8e0b-4d4e-9a77-2c1d5b9e0f41",
  "exercise": "squat",
  "video_url": "<temporary read link>"
}
```

A request with a missing field, or a `session_id` that is not a UUID, gets a `422` error that says which field is wrong.

`video_url` is a read-only link to the video that expires after about 15 minutes. Never log it: anyone with the link can watch the video until then.

`exercise` is one of `plank`, `shoulder_abduction`, `side_leg_raise`, `squat`, or `cat_cow` (see [Exercise names](../docs/analysis-result.md#exercise-names)).

Response: an `AnalysisResult`. Examples of every kind of result are in `docs/analysis-result-examples/`, such as this failure:

```json
{
  "status": "failed",
  "rep_count": null,
  "hold_seconds": null,
  "form_score": null,
  "reps": [],
  "feedback": [],
  "error_code": "no_person",
  "error_message": "We couldn't find a person in your video. Make sure your whole body is in the frame.",
  "analyzer_version": "0.1.0"
}
```

When a video cannot be analyzed (it is unreadable, too short or too long, has no person or several people, or the exercise is unknown), the answer is still `200`, with `status: "failed"`, an `error_code`, and its `error_message`. Build it with `AnalysisResult.failed(error_code, ANALYZER_VERSION)` so the message matches the list in [Failures](../docs/analysis-result.md#failures).

If the video cannot be downloaded from `video_url`, or our own code raises an unexpected error (a bug), catch it, log it without the video link, and return `AnalysisResult.failed("analysis_error", ANALYZER_VERSION)`. Use `video_unreadable` only for a downloaded file that ffmpeg cannot decode, because its message asks the patient to record again. The stub does not catch errors yet, so a crash is an HTTP 500, which the backend records as `analysis_unavailable`.

## Adding an exercise

1. Write its spec in `docs/exercises/`, following the template in [`docs/exercises/README.md`](../docs/exercises/README.md): camera angle, key joints, whether it is done in reps or held, what counts as one rep (or when a hold ends), and whether reps have a side. For each form rule: its threshold, and an issue code with a message (what went wrong), a tip (what to do), and a penalty. Also any metrics it reports, each name ending with its unit. See [`docs/analysis-result.md`](../docs/analysis-result.md) for how these fit the result.
2. Add a file in `app/analysis/exercises/` that follows the shared analyzer interface.
3. Ask the backend team to add its name to the `Exercise` table, with a new Alembic migration (never by hand). The name is a plain string, so the contract does not change.
4. Add labeled test clips and check it against the accuracy targets.
5. Raise `ANALYZER_VERSION` in `app/main.py`. Raise it too whenever anything else that can change a result changes, such as thresholds, penalties, or the shared framework.

## Scoring approach

Rule-based checks (joint angles and thresholds), not a trained model. No training data is needed, and every flag can be explained to a therapist.

Analyzers only report issues. The shared framework (SCRUM-50, Sprint 2) turns them into rep scores, the overall form score, and feedback, the same way for every exercise (see [Scoring](../docs/analysis-result.md#scoring) and [Feedback](../docs/analysis-result.md#feedback)).

## Data rules

- Synthetic or open-source data only. Never real patient data.
- Test videos live in the team OneDrive, never in git.
- The repo keeps only keypoint JSON (in `tests/fixtures/`) and at most one small open-source clip whose license allows it.

## Limits

Clips from 3 seconds to 2 minutes (`MIN_VIDEO_SECONDS` and `MAX_VIDEO_SECONDS` in `app/analysis_contract.py`). Two minutes leaves time for patients who move slowly. Target: a 2-minute clip analyzed in 3 minutes or less on Azure, counting from a cold start. Azure ends the backend's request to this service after 240 seconds, so there is little room above that target. The backend's and frontend's timeouts must be longer than 3 minutes (see [Clip limits and timing](../docs/analysis-result.md#clip-limits-and-timing)).

## Pull request CI

The shared workflow in `/.github/workflows/pr-ci.yml` runs three AI checks on every pull request, next to the API's checks:

- `AI lint`: ruff lint and formatting checks.
- `AI tests`: pytest with Python 3.12 and `requirements-dev.txt`. This includes the check that the backend's copy of `app/analysis_contract.py` matches ours, and that every example in `docs/analysis-result-examples/` matches the contract.
- `AI image build`: builds the `Dockerfile` without pushing an image. Then, inside the image, it loads OpenCV and MediaPipe (including MediaPipe's native code) and runs ffmpeg, so a missing system library fails the check. Last, it starts the image and waits for `/health` to answer.

Keep the job names stable: the repository ruleset matches checks by name (see `backend/README.md`, Required checks on main).
