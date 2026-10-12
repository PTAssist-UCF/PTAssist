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
  keypoints/            Video to body keypoints (Sprint 2)
  analysis/             Keypoints to reps, scores, and feedback (Sprint 2)
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

1. Write its spec in `docs/`: camera angle, key joints, whether it is done in reps or held, what counts as one rep (or when a hold ends), and whether reps have a side. For each form rule: its threshold, and an issue code with a message (what went wrong), a tip (what to do), and a penalty. Also any metrics it reports, each name ending with its unit. See [`docs/analysis-result.md`](../docs/analysis-result.md) for how these fit the result.
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
