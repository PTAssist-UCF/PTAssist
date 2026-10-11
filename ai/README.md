# AI service

Python service that turns an exercise video into a rep count, a form score, and feedback. It is internal only: the backend is the only caller, and it cannot be reached from the internet.

## Stack

FastAPI, OpenCV, ffmpeg, MediaPipe Pose, pytest, ruff. Runtime dependencies in `requirements.txt`; test and lint tools in `requirements-dev.txt`. MediaPipe, OpenCV, and NumPy are pinned to the same versions as the AI team's prototype.

## Layout

```
app/
  main.py      The web server: GET /health and POST /analyze
  schemas.py   The request and response shapes (Pydantic models)
  keypoints/   Video to body keypoints (Sprint 2)
  analysis/    Keypoints to reps, scores, and feedback (Sprint 2)
    exercises/ One file per exercise
tests/         pytest tests. fixtures/ holds keypoint JSON test data
Dockerfile     The service image: Python, ffmpeg, OpenCV, MediaPipe
```

## Run locally

Needs Python 3.12. Run these from `ai/`:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

uvicorn app.main:app --reload --port 8001   # http://localhost:8001/health and /docs
pytest
ruff check . && ruff format --check .
```

The service uses port 8001, so it can run next to the API on 8000. The API finds it through `AI_SERVICE_URL` in `/.env.example`. It needs no environment variables yet.

`/docs` is FastAPI's built-in page for trying the endpoints: open `POST /analyze`, click **Try it out**, and send a request.

pip installs OpenCV and MediaPipe but not ffmpeg, which is a separate program. The Docker image has it. To use it outside Docker, install it from https://ffmpeg.org/download.html.

## Docker

```bash
docker build -t ptassist-ai ai              # from the repo root
docker run --rm -p 8001:8001 ptassist-ai    # http://localhost:8001/health
```

The image starts from `python:3.12-slim`, installs ffmpeg and the system libraries OpenCV and MediaPipe need with `apt-get`, then installs `requirements.txt` with pip. It runs as a non-root user. The `Dockerfile` explains each step.

### In Docker Compose (SCRUM-19)

- The service listens on port 8001 inside its container. Other containers reach it by its Compose service name, for example `http://ai:8001`; that is the API's `AI_SERVICE_URL` in Compose.
- The image has no `curl`, so a Compose health check uses Python:

  ```yaml
  healthcheck:
    test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"]
  ```

- In Compose, video read links start with `http://azurite:10000/`, which this container can reach (see `backend/README.md`, Storage in Docker Compose).

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

## API

The service has no sign-in: it is internal only, and the backend is its only caller. The request and response shapes are the Pydantic models in `app/schemas.py`.

### `GET /health`

Returns `{"status": "ok"}` while the server is up. Docker and Azure use it to check the service.

### `POST /analyze`

**For now this is a stub:** it ignores the video and always returns the example response below. The real pipeline replaces it in Sprint 2.

Request (`session_id` is the backend's session id, a UUID):

```json
{
  "session_id": "3f6c1a52-8e0b-4d4e-9a77-2c1d5b9e0f41",
  "exercise": "exercise_1",
  "video_url": "<temporary read link>"
}
```

A request with a missing field, or a `session_id` that is not a UUID, gets a `422` error that says which field is wrong.

`video_url` is a read-only link to the video that expires after about 15 minutes. Never log it: anyone with the link can watch the video until then.

Response (draft, final schema set in task SCRUM-28):

```json
{
  "status": "complete",
  "rep_count": 3,
  "form_score": 82,
  "reps": [
    { "index": 1, "score": 90, "issues": [] },
    { "index": 2, "score": 85, "issues": [] },
    { "index": 3, "score": 71, "issues": ["too_fast"] }
  ],
  "feedback": ["Slow down on the way back up."],
  "error": null,
  "analyzer_version": "0.1.0-stub"
}
```

On bad input (no person found, clip too short or too long, unknown exercise), return `status: "failed"` with a clear `error`.

## Adding an exercise

1. Write its spec in `docs/`: camera angle, key joints, what counts as one rep, form rules, feedback wording.
2. Add a file in `app/analysis/exercises/` that follows the shared analyzer interface.
3. Add labeled test clips and check it against the accuracy targets.

## Scoring approach

Rule-based checks (joint angles and thresholds), not a trained model. No training data is needed, and every flag can be explained to a therapist.

## Data rules

- Synthetic or open-source data only. Never real patient data.
- Test videos live in the team OneDrive, never in git.
- The repo keeps only keypoint JSON (in `tests/fixtures/`) and at most one small open-source clip whose license allows it.

## Limits

Clips up to 60 seconds. Target: a 60-second clip analyzed in 90 seconds or less on Azure.

## Pull request CI

The shared workflow in `/.github/workflows/pr-ci.yml` runs three AI checks on every pull request, next to the API's checks:

- `AI lint`: ruff lint and formatting checks.
- `AI tests`: pytest with Python 3.12 and `requirements-dev.txt`.
- `AI image build`: builds the `Dockerfile` without pushing an image. Then, inside the image, it loads OpenCV and MediaPipe (including MediaPipe's native code) and runs ffmpeg, so a missing system library fails the check. Last, it starts the image and waits for `/health` to answer.

Keep the job names stable: the repository ruleset matches checks by name (see `backend/README.md`, Required checks on main).
