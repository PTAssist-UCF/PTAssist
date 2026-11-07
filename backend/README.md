# Backend

FastAPI service. It is the only entry point into PTAssist: the frontend talks only to this API, and only this API talks to the database, storage, and AI service.

## Stack

FastAPI, SQLAlchemy, Alembic, PostgreSQL (psycopg 3 driver), Clerk's Python SDK (`clerk-backend-api`), the Azure Blob SDK (`azure-storage-blob`), httpx (calls to the AI service), pytest, ruff. Runtime dependencies in `requirements.txt`; test and lint tools in `requirements-dev.txt`.

## Layout

```
app/
  main.py    Creates the FastAPI app and includes the routers
  config.py  Settings from environment variables
  db.py      SQLAlchemy engine and the get_db session dependency
  seed.py    Local dev data: a linked therapist and patient with a plan (see Dev data)
  routes/    HTTP endpoints, grouped by area
  schemas/   Request and response models (Pydantic). analysis_contract.py is a copy, see Analysis results
  models/    Database tables (SQLAlchemy). Base class in base.py
  auth/      Clerk token check, current user, role and ownership checks
  storage/   Video storage: upload, temporary read links, delete (Azurite locally, Azure Blob in the cloud)
  jobs/      Background task that calls the AI service
migrations/  Alembic migrations (versions/ holds one file per migration)
tests/
alembic.ini  Alembic settings
Dockerfile   API image, also used to run migrations
```

## Run locally

Video uploads also need `ffprobe` on `PATH` (installed by the ffmpeg package). The
API Docker image includes it. If running Python outside Docker, install ffmpeg
from its official distribution and check `ffprobe -version`. The API can start
without it, but video validation then returns `503`.

Needs Python 3.12, plus Postgres and Azurite for storage. The simplest way to get both is Docker Compose: run `docker compose up -d db azurite` from the repo root (see the root README, Getting started). `DATABASE_URL` and `STORAGE_CONNECTION_STRING` in `/.env.example` already point at them. Then run these from `backend/`:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp ../.env.example ../.env       # once, then fill in the Clerk values (see Config)
set -a; source ../.env; set +a   # load the settings into this shell (macOS/Linux)
alembic upgrade head
uvicorn app.main:app --reload    # http://localhost:8000/health and /docs

pytest                           # needs the test database and Azurite, see Testing
ruff check . && ruff format --check .
```

`GET /health` returns `{"status": "ok"}`. It needs no token and does not touch the database, so Docker and Azure can use it as a liveness probe.

To try `GET /me` in `/docs`, click **Authorize** and paste a Clerk session token. In the browser console of the signed-in web app, `await window.Clerk.session.getToken()` prints one. It expires after 60 seconds.

## Docker

```bash
docker build -t ptassist-api backend      # from the repo root
docker run --rm -p 8000:8000 -e DATABASE_URL=<url> -e CLERK_SECRET_KEY=<key> \
  -e CLERK_AUTHORIZED_PARTIES=<origins> -e STORAGE_CONNECTION_STRING=<connection string> \
  ptassist-api
```

The same image runs migrations: `docker run --rm -e DATABASE_URL=<url> ptassist-api alembic upgrade head`.

To run the API with its database, storage, and the AI service, use Docker Compose (root README, Getting started). There the `api` service runs `alembic upgrade head` each time it starts, then the server.

## Migrations

Alembic reads `DATABASE_URL` from the environment (it is not stored in `alembic.ini`).

```bash
alembic upgrade head                                   # apply all migrations
alembic revision --autogenerate -m "add user table"    # create a new one
```

To add a table: create the model in `app/models/`, import it in `app/models/__init__.py` (so autogenerate can see it), then run `alembic revision --autogenerate`. Always read the generated file before committing. New migrations are linted and formatted with ruff automatically. Constraint and index names follow the naming convention in `app/models/base.py`. `tests/test_migrations.py` fails if the models and the migrations don't match.

Rows every database needs, like the exercise library, are added by a migration too (see `op.bulk_insert` in `migrations/versions/c35bebbdd455_add_core_data_model.py`), never by hand.

## Dev data (seed)

`app/seed.py` fills your local database with a therapist, a patient linked to them, and a plan with all 5 exercises. Run it from `backend/` after `alembic upgrade head`, with `DATABASE_URL` set to your local database. Never run it against Azure.

```bash
python -m app.seed                                   # a placeholder patient
python -m app.seed --patient-email you@example.com   # give the plan to your own account
```

In Docker Compose, run it in the `api` container: `docker compose exec api python -m app.seed`.

The placeholder users (`therapist@example.com` and `patient@example.com`) have no Clerk account, so nobody can sign in as them. To see the plan in the web app, sign in once (which creates your user as a patient), then run the seed with `--patient-email` and your email. Running it again adds nothing new. The targets are made-up numbers for testing, not clinical advice.

## Every request

1. Verify the Clerk token. No valid token means `401`.
2. Load the user from our `User` table. First call from a new user creates them as a patient.
3. Check the role (patient or therapist). Wrong role means `403`.
4. Check ownership: patients see only their own data, therapists see only linked patients. Not yours means `404`.

Steps 1 and 2 are the `CurrentUser` dependency (see Sign-in). For step 3, a therapist-only route takes `CurrentTherapist` instead, from the same file: it answers `403` to anyone who is not a therapist. For step 4, `get_link` in `app/auth/ownership.py` returns a therapist's link to a patient, or `None` when they are not linked.

Roles live in our database, not in Clerk. Therapists are promoted by the team with a script.

## Sign-in (Clerk)

Steps 1 and 2 are the `CurrentUser` dependency in `app/auth/current_user.py`. A route that takes it only runs for a signed-in user:

```python
@router.get("/me")
def get_me(user: CurrentUser) -> MeResponse: ...
```

The web app sends the Clerk session token as `Authorization: Bearer <token>`. `app/auth/clerk.py` checks it with Clerk's Python SDK, and it is the only code that talks to Clerk:

- Only session tokens are accepted, not Clerk API keys or machine tokens.
- The signature must match our Clerk instance's public keys. The SDK fetches them with `CLERK_SECRET_KEY` and caches them for 5 minutes.
- The token must not be expired, and its `azp` claim (the origin of the page that asked for it) must be in `CLERK_AUTHORIZED_PARTIES`.

On a user's first request, the API asks Clerk's Backend API for their primary email and creates their `users` row as a patient. Later requests only read the row. The email is copied once: if the user changes it in Clerk, our copy keeps the old one.

| Status | When |
| --- | --- |
| `401` | No bearer token, or the token is invalid, expired, or from another origin. `detail` says why |
| `403` | First request from a Clerk account that has no email address. Nothing is saved |
| `503` | Clerk could not be reached to check the token or look up the email, or Clerk refused `CLERK_SECRET_KEY` (for example a mistyped or cut-off key). Nothing is saved; try again, or check the key |
| `500` | `CLERK_SECRET_KEY` is not set on the API (a setup mistake). `detail` says so, and the web app shows it |

Never log tokens or emails. The database engine hides query values (`hide_parameters`), so they also stay out of SQL logs and error messages.

### Clerk settings

- `CLERK_SECRET_KEY` is the development instance's secret key (`sk_test_...`) from the **API keys** page of the Clerk Dashboard. It gives full access to our Clerk instance: keep it in `/.env` locally and in an Azure secret in the cloud, never in code.
- Users must sign up with an email address (Clerk Dashboard, **User & authentication**). The API needs it to create their row.
- `CLERK_AUTHORIZED_PARTIES` lists the web app's origins: `http://localhost:5173` (the Vite dev server) locally, and the Static Web Apps URL in Azure. It is also the list of origins that browsers may call the API from (see Browser access).

Until the promote script exists (SCRUM-65), promote a local test account by hand: `UPDATE users SET role = 'therapist' WHERE email = '<email>';`

### Browser access (CORS)

The web app and the API run on different origins: `http://localhost:5173` and `http://localhost:8000` locally, and the Static Web Apps URL and the API's Container Apps URL in Azure. A browser only lets the web app read the API's answers if the API names the web app's origin as allowed. This is CORS, set up in `app/main.py`. Before a request that carries a token, the browser first asks with an `OPTIONS` request (a "preflight").

- **The allowed origins are the ones in `CLERK_AUTHORIZED_PARTIES`**, the same list sign-in checks, so there is one list of web app origins to keep up to date. A page on any other origin can't read the API's answers.
- **Allowed methods and headers:** `GET`, `POST`, `PUT`, `PATCH`, and `DELETE`, with the headers `Authorization` and `Content-Type`. Cookies are not allowed, because the token travels in the `Authorization` header.
- **Error answers reach the web app too:** a `401` arrives as a `401`, so the web app can send the user to sign in. This holds for every answer made with `HTTPException`. A crash is different: when a route raises any other error, the `500` it produces has no CORS headers, so the browser hides it and the web app only sees "Failed to fetch" (the error is in the API's log). So answer expected problems with `HTTPException`, as `get_clerk` does for a missing `CLERK_SECRET_KEY`.
- **If the browser says "Failed to fetch"**, often with a CORS error in its console, either the API isn't running, the request crashed (see the API's log), or the page's origin is missing from `CLERK_AUTHORIZED_PARTIES`. For the last one, add it (comma-separated) and restart the API. In Azure, the list must hold the Static Web Apps URL (see `infra/README.md`). If the list is empty, no browser can call the API.
- **CORS only limits browsers.** Other programs can still send requests, so every route still checks the token, the role, and ownership.

`tests/test_cors.py` checks that the web app's origin is allowed, other origins are not, and error answers carry the CORS headers.

## Data model

| Model (table) | File | Holds |
| --- | --- | --- |
| `User` (`users`) | `user.py` | Clerk id, email, role (`patient` or `therapist`), created time |
| `TherapistPatient` (`therapist_patients`) | `therapist_patient.py` | Which therapist is linked to which patient |
| `Exercise` (`exercises`) | `exercise.py` | The exercise library: its name in the API, such as `squat`, a display name, and its kind: `reps`, or `hold` for the plank |
| `Plan` (`plans`) | `plan.py` | A therapist's plan for one patient |
| `PlanExercise` (`plan_exercises`) | `plan.py` | An exercise in a plan, with targets: reps per set (or a hold time in seconds for a hold exercise), sets, and times per week |
| `ExerciseSession` (`sessions`) | `session.py` | One uploaded video (one set) for a plan exercise, with its status: `processing`, `complete`, or `failed` |
| `SessionResult` (`session_results`) | `session.py` | The analysis result of a finished session, complete or failed, in one JSONB column (see Analysis results) |

```
users ──< therapist_patients >── users        (therapist, patient)
users ──< plans ──< plan_exercises >── exercises
                    plan_exercises ──< sessions ──── session_results (0 or 1)
```

Table names are plural snake_case (`users`), and primary keys are UUIDs (see `app/models/user.py`). The schema changes only through Alembic migrations. Never edit the database by hand, and never change a migration after it is merged.

How the tables fit together, and why (SCRUM-43):

- **The session model is `ExerciseSession`**, not `Session`, because routes also use SQLAlchemy's `Session` for the database connection. The table is still `sessions`, and the API still says "session".
- **Exercises are rows, added by migrations.** The migration that creates `exercises` also adds the 5 exercises, so every database has them, Azure included. `name` is plain text, not a database enum, and other tables point at the exercise's `id`, so adding or renaming an exercise is a new migration that adds or changes a row. Its `name` must match the AI service's (`docs/analysis-result.md`, Exercise names).
- **A plan exercise has either `reps` or `hold_seconds`**, never both: reps per set for exercises done in reps, a hold time for the plank. Both kinds have `sets`. One video is one set, so `sets` is how many videos to upload each time, and `times_per_week` is how many days a week (1 to 7). The database checks that exactly one target is set and that targets are positive. It can't check that the target fits the exercise's kind, so the plan endpoints must (SCRUM-63). For `side_leg_raise`, `reps` counts both sides together, like the result's `rep_count`.
- **Ownership goes through the plan.** A session belongs to a plan exercise, which belongs to a plan, whose `patient_id` is the owner. A therapist may see it if they are linked to that patient in `therapist_patients`. The database can't check roles (they are in `users`), so routes check that the therapist in a link or plan is a therapist and the patient a patient.
- **A session has at most one result.** `session_results.session_id` is its primary key. The failure reason is inside the JSON, not on the session (`docs/analysis-result.md`, How the backend stores it).
- **Results are kept.** A plan exercise that has sessions can't be deleted (the foreign key refuses), so changing a plan must not delete exercises that have uploads.
- **Each link is stored once:** the same therapist and patient can't be linked twice, and nobody can be linked to themselves. A patient may have several therapists, and several plans. Whether a patient gets only one plan at a time is decided with the plan endpoints (SCRUM-63).

## Session lifecycle

```
upload -> processing -> complete
                     -> failed (with a reason)
```

1. `POST` upload: validate the file (type, size, and length between `MIN_VIDEO_SECONDS` and `MAX_VIDEO_SECONDS` from `app/schemas/analysis_contract.py`, currently 3 seconds to 2 minutes; import them, don't hard-code them), store it, create the `Session` as `processing`. A file that fails these checks gets an HTTP error, and no session is created.
2. A FastAPI background task (`app/jobs/analysis.py`, see [Background analysis](#background-analysis-scrum-45)) creates a 15-minute read link and calls the AI service `POST /analyze`.
3. The result is checked against the contract and saved to `SessionResult`, and the session's status becomes the result's `status`: `complete` or `failed`, in the same transaction.
4. If there is no valid result, the backend saves a failed result itself: `analysis_unavailable` when the AI service could not be reached, answered with an error, or sent a result that does not match the contract, and `analysis_timed_out` when it did not answer in time.
5. Sessions stuck in `processing` too long are also saved as failed, with `analysis_timed_out` (SCRUM-66, not built yet).

A session's result is saved once: after a session is `complete` or `failed` it never changes, and a later answer for it is dropped.

The AI service may take up to 3 minutes for a 2-minute clip, counting from a cold start. On Azure, Container Apps ends any HTTP request after 240 seconds, so the timeout in step 2 (`AI_SERVICE_TIMEOUT_SECONDS`, 230 seconds by default) must be between 3 and 4 minutes. The stuck cutoff in step 5 must be longer than that timeout, so the cleanup never fails a session the background task is still waiting on. See [Clip limits and timing](../docs/analysis-result.md#clip-limits-and-timing).

The frontend polls the session status. Once it is `complete` or `failed`, the `SessionResult` has the details, including the failure reason. Later, a job queue can replace the background task without changing the API.

## Analysis results

A `SessionResult` holds one analysis result: the rep count (or hold time), form score, details for each rep, feedback, and the failure reason if it failed. Its shape, the error codes, and the rules behind it are described in [`docs/analysis-result.md`](../docs/analysis-result.md).

The shape is defined by the Pydantic models in `app/schemas/analysis_contract.py`. **That file is an exact copy of `ai/app/analysis_contract.py`, which the AI service owns. Never edit the copy by hand.** To change the contract, edit the AI service's file, then copy it over from the repo root:

```bash
cp ai/app/analysis_contract.py backend/app/schemas/analysis_contract.py
```

`tests/test_analysis_contract.py` fails if the two files differ, and this check must pass before a pull request can merge. It also loads every example in `docs/analysis-result-examples/`. The backend's ruff skips the copy (`extend-exclude` in `pyproject.toml`), because the AI service's lint already checks the original.

- Check every result from the AI service with `AnalysisResult.model_validate(...)` before saving it. An answer that does not match is saved as `analysis_unavailable`.
- Record your own failures with `AnalysisResult.failed("analysis_timed_out", analyzer_version=None)` (or `"analysis_unavailable"`), so they have the same shape and the standard patient message.
- Store the whole result in one JSONB column. Results are kept, so the contract only ever gains fields (see [Changing the contract](../docs/analysis-result.md#changing-the-contract)).

## Endpoints (draft)

Final paths are decided in each task.

Each route's function name becomes its operation id in the API description (`/openapi.json`), and the frontend's generated hooks are named after it: `def get_me` becomes `useGetMe()`. So give route functions clear names, and never reuse one; `tests/test_openapi.py` checks they are unique. Also give each router a tag, as in `routes/me.py` (`tags=["me"]`): the tag names the generated file (`src/api/me.ts`), and a route without one lands in `src/api/default.ts`. After changing the API, regenerate the frontend's hooks (see `frontend/README.md`, Talking to the API).

| Area | Endpoint | Who |
| --- | --- | --- |
| Me | `GET /me` | Anyone signed in |
| Exercises | `GET /exercises` | Anyone signed in |
| Patients | `GET/POST /therapist/patients`, `DELETE /therapist/patients/{patient_id}` | Therapist |
| Plans | `POST/PUT /plans`, `GET /plans/me` | Therapist, patient |
| Sessions | `POST /sessions`, `GET /sessions/{id}`, `GET /sessions` | Patient (therapist can read linked patients') |
| Progress | `GET /patients/{id}/progress` | Therapist |

## Linking patients (SCRUM-62)

A therapist links a patient by the email the patient signed in with, and then sees only their linked patients' data. These endpoints are for therapists only: anyone else, patients included, gets `403`.

| Endpoint | Does | Success |
| --- | --- | --- |
| `POST /therapist/patients` with `{"email": "..."}` | Links the patient who uses that email | `201` with the linked patient |
| `GET /therapist/patients` | Lists the caller's linked patients, ordered by email | `200` with a list (empty if none) |
| `DELETE /therapist/patients/{patient_id}` | Removes the caller's link to that patient | `204`, no body |

A linked patient is `{"id", "email", "linked_at"}`: the patient's user id (the `patient_id` to unlink), their email, and when this therapist linked them.

- **Finding the patient.** The email is compared ignoring case and the spaces around it, and only with patients. The patient must have signed in once, so that their user exists. An email that no patient uses gets `404` with the same message whether nobody or a therapist uses it, so the answer doesn't tell who has an account. This also means nobody can link themselves: the caller is a therapist, not a patient.
- **Linking twice gets `409`**, also when two requests arrive at once (the database keeps one link per pair). The existing link stays as it was.
- **An email that two patients use gets `409`.** Our copy of an email is never updated (see Sign-in), so an old user row can share its email with a newer one. The API never guesses which patient is meant; the team fixes the data.
- **A patient can have several therapists.** Each therapist sees only their own links.
- **Unlinking removes only the link.** A patient the caller is not linked to (an unknown id, or another therapist's patient) gets `404`, not `403`, so the answer doesn't tell who is linked to whom. Plans, sessions, and results are kept (results are never deleted). The therapist just stops seeing them, because every therapist check goes through the link, and sees them again after linking the patient again. What happens to a plan whose therapist is no longer linked (for example, whether the patient still sees it and uploads to it) is decided with the plan endpoints (SCRUM-63).

| Status | When |
| --- | --- |
| `401` | No valid token |
| `403` | The caller is not a therapist |
| `404` | Link: no patient uses that email. Unlink: the caller is not linked to that patient |
| `409` | Link: already linked, or more than one patient uses that email |
| `422` | Link: the email is missing, blank, longer than 320 characters, or contains a NUL character |

**Frontend handoff:** router tag `patients`; operation ids `link_patient`, `list_linked_patients`, and `unlink_patient`. Regenerate the hooks from the running API (`npm run generate:api`); the generated frontend files are left to the frontend team. To try the endpoints in `/docs`, promote your local account to therapist first (see Clerk settings). `tests/test_therapist_patients.py` covers each endpoint, including the wrong role and the wrong owner.

## Video upload and session status (SCRUM-44)

`POST /sessions` accepts a `multipart/form-data` request with two required fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `plan_exercise_id` | UUID text | An assigned exercise whose plan belongs to the signed-in patient |
| `video` | File | One MP4, MOV, or WebM recording (one set) |

Send the Clerk token in `Authorization: Bearer <token>`. The route accepts patients
only (`403` for therapists). A missing assignment or another patient's assignment
returns `404`, before inspecting media or writing a blob. Filenames are never used
as storage keys: the API generates a UUID and stores `sessions/<uuid>.<extension>`.

Validation checks the actual uploaded size, not a caller's size claim. The default
limit is **500 MiB** (`MAX_VIDEO_UPLOAD_BYTES=524288000`), which fits two-minute
1080p phone recordings. 4K recordings may exceed it: record at 1080p, or raise the
limit deliberately (mind the temporary disk, below). FastAPI spools multipart
files to temporary disk; this check happens after multipart parsing, not as a
network/request-body rate or size guard. Infrastructure limits and further upload
hardening belong to SCRUM-82. While it checks an upload, the API holds about twice
its size on temporary disk (the spooled file plus an inspection copy), and Azure
Container Apps gives a container only about 1-4 GiB of it, depending on its CPU
size. A higher limit leaves room for fewer uploads at once. Neither copy is kept
after the request.

`ffprobe` inspects the actual media container and checks for a video stream (audio
and cover art alone do not count). The inspected type must match the extension:
`.webm` for WebM, and `.mp4` or `.mov` for the MP4/QuickTime family, which phones
name loosely (for example an ISO MP4 saved as `.mov`). The blob gets the inspected
container's extension and a trusted content type derived by the API (`video/mp4`,
`video/quicktime`, or `video/webm`), never the request's arbitrary content type.
Inspection has a 15-second timeout, permits only local-file protocols and the
supported container demuxers, and its output is never returned or logged. A
timeout answers `503`, not `422`: it means the API was too slow, not that the video
is bad, so the patient is not asked to record again. Videos must be between `MIN_VIDEO_SECONDS`
and `MAX_VIDEO_SECONDS` from `app/schemas/analysis_contract.py`, currently 3-120
seconds, inclusive. The container duration is checked too, so a long audio track
cannot extend a clip past the maximum. This is media metadata validation, not full
decoding or pose analysis; the AI service retains its own input checks.

| Response | Meaning |
| --- | --- |
| `201` | Private blob saved and session committed as `processing` |
| `401` | Missing or invalid Clerk token |
| `403` | The signed-in user cannot upload in their role |
| `404` | Assignment is missing or not owned by this patient |
| `413` | File exceeds `MAX_VIDEO_UPLOAD_BYTES` |
| `415` | Unsupported declared type/extension or inspected format mismatch |
| `422` | Invalid form, empty/unreadable media, no video, or duration outside the shared limits |
| `503` | Inspection tool unavailable or timed out, or upload/database write failed |

Rejected videos do not create a session or call `storage.upload`. The route holds no
database connection while it checks and stores the video, which can take minutes: it
ends the transaction of the sign-in and ownership checks first (otherwise a few slow
uploads would use up the connection pool), uploads the blob, and only then inserts
and commits the session in a short transaction. If uploading or committing the
session fails, the transaction is rolled back and blob deletion is attempted,
including for a partially uploaded blob, so no blob is left without a session and no
session without its video. Cleanup failure is logged using
only the generated session UUID. Since PostgreSQL and blob storage do not share a
transaction, an outage during compensating deletion can leave an orphan blob for
later cleanup. The existing storage dependency still reports missing/broken storage
configuration as described under Storage and Config.

Both the `201` acknowledgement and `GET /sessions/{session_id}` return:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | UUID | Session identifier used for polling |
| `plan_exercise_id` | UUID | Assigned exercise for this recording |
| `status` | `processing`, `complete`, or `failed` | Current saved state |
| `created_at` | Time with timezone | When the session was created |

Status is visible to the owning patient and therapists currently linked to that
patient. Other patients, unlinked therapists, and unknown IDs receive `404`.
The response never exposes a private storage key or a signed video URL. Results
and progress are handled separately in SCRUM-64.

**Analysis starts after the response.** Once the session is committed, the route
schedules the background analysis (next section) and answers `201` with the session
`processing`; the frontend polls `GET /sessions/{session_id}` until it is `complete`
or `failed`. The analysis reads `session.video_key` and gets a temporary read URL
through `app/storage/`. Migration `e846d97b14af` adds the unique key, and
`163e3f3a47c4` makes it required (`NOT NULL`), so every session has a stored video.
No session can lack a key (the upload route is the only code that creates sessions),
so that migration neither fills in nor deletes rows: if one without a key exists
anyway, it stops with "contains null values" and changes nothing, rather than
deleting the session and its result.

**Frontend handoff:** router tag `sessions`; operation IDs `create_session` and
`get_session`. The API describes the upload form and `SessionResponse` in
`/openapi.json`. The frontend team must regenerate Orval hooks from the running
API (`npm run generate:api`); generated frontend files were deliberately left for
that team. In `/docs`, authorize, select `POST /sessions`, enter an owned plan
exercise UUID, choose a video, and execute. Use the returned `id` in the GET route.

`tests/test_sessions.py` generates tiny synthetic videos in pytest's temporary
directory with ffmpeg (no recordings are committed). It exercises real ffprobe,
Postgres, and Azurite for uploads, permission checks, duration boundaries, private
retrieval, rollback cleanup, and that no database connection is held while a video
is checked and stored. `tests/test_uploads.py` covers inspection errors.

## Background analysis (SCRUM-45)

`app/jobs/analysis.py` has the job: `analyze_session(session_id)`. `POST /sessions`
schedules it as a FastAPI background task once the session is committed, so it runs
after the `201` is sent. Before that, the route closes the upload's temporary file:
FastAPI would otherwise keep it on disk until the analysis ends. The job:

1. Loads the session's status, `video_key`, and exercise name in a short read, so
   no database connection is held during the call. A session that is gone or no
   longer `processing` is skipped, without calling the AI service.
2. Makes a 15-minute read link with `storage.read_url` and sends `AnalyzeRequest`
   (session id, exercise name, link) to `POST {AI_SERVICE_URL}/analyze` with httpx.
   It waits up to 10 seconds to connect and `AI_SERVICE_TIMEOUT_SECONDS` (default
   230) for the answer.
3. Checks the answer with `AnalysisResult.model_validate`, then saves it in one
   transaction: it locks the session's row, and only if the session is still
   `processing` adds the `SessionResult` and sets the status to the result's
   `status`. Otherwise the answer is dropped, so a result is saved once.

| What happens | Saved result |
| --- | --- |
| `200` with a valid complete result | The result as sent; status `complete` |
| `200` with a valid failed result (the AI service's own failure, such as `no_person`) | The result as sent; status `failed` |
| Any other status (such as a `500` crash, or `422` for a request it refused) | `analysis_unavailable` |
| An answer that is not JSON or does not match the contract | `analysis_unavailable` |
| No connection: refused, unknown host, no connection within 10 seconds, or the connection broke | `analysis_unavailable` |
| No answer within `AI_SERVICE_TIMEOUT_SECONDS` | `analysis_timed_out` |
| An empty `video_key` (the AI service is not called) | `analysis_unavailable` |
| Any other error in the job, such as a bug | `analysis_unavailable` |
| The database refuses the result (for example text with the character `\u0000`) | `analysis_unavailable` in its place |

The backend's own failures are `AnalysisResult.failed(code, analyzer_version=None)`,
so they meet the contract and carry the standard patient message. Every path ends
`complete` or `failed`, except one: if the database itself can't be reached, nothing
can be saved, and the session stays `processing` until the stuck-session cleanup
(SCRUM-66). The same happens if the API container stops during an analysis (a deploy,
or scaling in).

Log lines carry only the session id and the outcome (such as "failed with
analysis_timed_out: no answer in time"), never the read link, an exception's
message, or the AI service's answer. Only `WARNING` and above show without logging
configuration, which covers every failure.

Each running analysis waits in one of the API's worker threads, the same pool of 40
threads (anyio's default) that runs its other routes. That is plenty for the proof
of concept; the job queue planned as a stretch goal would remove the limit.

Until the real pipeline is connected (SCRUM-52), the AI service's `POST /analyze` is
a stub that returns made-up results, so a local upload ends `complete` with those.

Tests never call the AI service: see Testing. `tests/test_analysis_job.py` covers
each row above, a session that finishes during the call, and a job that runs twice.
It uses real sockets for an AI service that is down or never answers.

## Storage

`app/storage/blob.py` is the only code that talks to storage. It uses the Azure Blob SDK against Azurite (Microsoft's Azure Storage emulator) locally and our Azure storage account in the cloud. There is one code path: only `STORAGE_CONNECTION_STRING` changes. Routes get it with the `get_storage` dependency, which tests can swap:

```python
storage: Annotated[Storage, Depends(get_storage)]  # a route parameter

storage.upload(key, upload_file.file, "video/mp4")  # bytes or a binary file object
link = storage.read_url(key)  # read-only link to this one file, for 15 minutes
storage.delete(key)  # no error if it is already gone
```

- Files live in one private container, `STORAGE_CONTAINER`. The first `get_storage` call creates it without public access, and refuses a container that allows public access. Other code never talks to Azurite or Azure directly, and never makes a file public.
- A key is the file's name in the container, such as `sessions/<session id>.mp4`: `/`-separated parts of letters, digits, `.`, `_`, and `-`. `upload`, `read_url`, and `delete` raise `ValueError` for any other key. `upload` replaces a file with the same key, so the API makes keys itself and never takes them from the request. Keys hold only ids, never names or emails: the Azure SDK logs request URLs, keys included, when INFO logging is on.
- The API also sets `content_type` itself (a fixed video type, after checking the file), never copying the request's `Content-Type`. Read links serve the file with that type, so a type like `text/html` would let the file run as a web page.
- `upload` reads a file object from its current position, 4 MB at a time, so it never holds a whole large video in memory.
- Files are read only through `read_url`: a link (SAS URL) that can read that one file and nothing else. It expires after 15 minutes by default, and `read_url` refuses a longer lifetime (SCRUM-85). It starts 5 minutes in the past, so storage whose clock is slightly behind still accepts it. In Azure it works over HTTPS only; Azurite serves plain HTTP.
- Anyone with a read link can read the file until it expires, so treat it as a secret. Never log a link, its query string, or file contents, and pass it only to the service that needs it.
- If storage refuses the connection, calls fail within a few seconds (3 quick retries). If it does not answer, each of the 4 tries waits up to 5 seconds to connect, about 25 seconds in all. Once connected, each try waits up to 60 seconds for a reply (the SDK's default), which a slow 4 MB block upload can need. Either way the route returns `500`.
- Raw videos are deleted after 30 days by a lifecycle rule on the Azure storage account (SCRUM-81). Azurite emulates only reading and writing files, not account settings like this rule, so it has no equivalent: local files stay until you delete them.

### Storage in Docker Compose

`UseDevelopmentStorage=true` always means Azurite on `127.0.0.1:10000`, and inside a container `127.0.0.1` is the container itself. So an API container, including the `docker run` in Docker above, needs the full connection string with Azurite's address. `/compose.yaml` gives the `api` service this one, where `azurite` is Azurite's service name:

```
DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=${AZURITE_ACCOUNT_KEY};BlobEndpoint=http://azurite:10000/devstoreaccount1;
```

`AZURITE_ACCOUNT_KEY` is Azurite's well-known development key, published in Microsoft's Azurite documentation (the link is in `/.env.example`). It is not a real secret, but GitHub secret scanning flags it like any Azure storage key and may block the push, so it is not in the repo: each developer puts it in their own `/.env` (never committed). Without it the stack still starts and `/health` works, but storage calls in the Compose API fail with "The storage connection string has no account key to sign read links".

Compose sets the `api` service's other settings itself and takes only `CLERK_SECRET_KEY`, `CLERK_AUTHORIZED_PARTIES`, and `AZURITE_ACCOUNT_KEY` from `/.env`. The other values in `/.env`, such as `DATABASE_URL` and `STORAGE_CONNECTION_STRING` (`UseDevelopmentStorage=true`), are for running the API on your computer.

Read links made in Compose start with `http://azurite:10000/`. The AI service container can open them; your browser cannot, because only containers in the stack know the name `azurite`.

## Config

Read from environment variables (see `/.env.example`): database URL, Clerk settings, storage settings, and the AI service's URL and timeout. No secrets in code. Settings are defined in `app/config.py`. Add new ones there and in `/.env.example`.

| Variable | Read by | What |
| --- | --- | --- |
| `DATABASE_URL` | API, Alembic | Postgres URL. Must use the `postgresql+psycopg://` scheme so SQLAlchemy picks the psycopg 3 driver |
| `CLERK_SECRET_KEY` | API | Clerk secret key, to check tokens and look up new users' emails. Secret. See Clerk settings |
| `CLERK_AUTHORIZED_PARTIES` | API | Web app origins, comma-separated. Tokens must come from one of them, and browsers may call the API only from them (CORS). Empty skips the token's origin check and blocks every browser, so set it everywhere |
| `STORAGE_CONNECTION_STRING` | API | Storage account to use. `UseDevelopmentStorage=true` locally (Azurite on `127.0.0.1:10000`). In Azure, the storage account's connection string: it holds the account key, so it is a secret. See Storage |
| `STORAGE_CONTAINER` | API | Private blob container for videos. Default `videos`. Created if missing |
| `MAX_VIDEO_UPLOAD_BYTES` | API, Docker Compose | Maximum uploaded video size in bytes; positive integer, default 524288000 (500 MiB). The API needs about twice this in temporary disk space per upload being checked. Independent of the shared duration limits |
| `AI_SERVICE_URL` | API | Where the background analysis sends `POST /analyze`. Default `http://localhost:8001`. Docker Compose sets `http://ai:8001`; in Azure, the AI container app's internal URL. See Background analysis |
| `AI_SERVICE_TIMEOUT_SECONDS` | API | Seconds to wait for `POST /analyze` to answer before the session fails with `analysis_timed_out`. Positive number, default 230. In Azure keep it between 180 and 240 (see Session lifecycle) |
| `TEST_DATABASE_URL` | pytest | The test database. See Testing |
| `TEST_STORAGE_CONNECTION_STRING` | pytest | The test storage, by default `UseDevelopmentStorage=true`. See Testing |
| `AZURITE_ACCOUNT_KEY` | Docker Compose | Azurite's well-known key, for the `api` service's connection string. Not read by the API itself. See Storage in Docker Compose |

Alembic only needs `DATABASE_URL`. Without `CLERK_SECRET_KEY` the API still starts (and logs a warning about it), but every route that needs sign-in fails with `500` and a `detail` that names the missing key (the web app shows it). Without `STORAGE_CONNECTION_STRING` it also starts, but anything that uses storage fails with `500`.

A connection string contains `;`, so in `/.env` wrap any value other than `UseDevelopmentStorage=true` in double quotes, or `source` splits it.

## Testing

pytest, against a real Postgres database: `TEST_DATABASE_URL`, by default `postgresql+psycopg://ptassist:ptassist@localhost:5433/ptassist_test`. Tests always use it in place of `DATABASE_URL`. Each run builds the schema with `alembic upgrade head`, empties the tables before every test, and drops everything at the end with `alembic downgrade base`, so every run also checks that the migrations work both ways. Tables the migrations fill in (`exercises`) are not emptied (`MIGRATION_DATA_TABLES` in `tests/conftest.py`), so tests must not change them. Never point it at a database you want to keep.

Start the test database once with Docker. It uses port 5433 so it does not clash with the Compose database (5434) or a Postgres installed on your computer (5432):

```bash
docker run -d --name ptassist-test-db -p 5433:5432 \
  -e POSTGRES_USER=ptassist -e POSTGRES_PASSWORD=ptassist -e POSTGRES_DB=ptassist_test \
  postgres:17
```

After a reboot, run `docker start ptassist-test-db`. Without Docker, create an empty database in any local Postgres 17 and set `TEST_DATABASE_URL` to it.

Storage tests run against real Azurite, never Azure: `TEST_STORAGE_CONNECTION_STRING`, by default `UseDevelopmentStorage=true` (Azurite on `127.0.0.1:10000`). Tests always use it in place of `STORAGE_CONNECTION_STRING`, and fail for any account other than Azurite's `devstoreaccount1`. Each run creates its own container (`test-<random>`) and deletes it at the end. Storage tests do not need Postgres. If Azurite is not running, they fail with a message that points here.

Only one Azurite can use port 10000 at a time. If the Compose stack is running, the tests use its Azurite, so skip this step. If you created `ptassist-test-storage` earlier, run `docker stop ptassist-test-storage` before `docker compose up`, or Compose fails with "port is already allocated". Otherwise start Azurite once with Docker (blob service only):

```bash
docker run -d --name ptassist-test-storage -p 10000:10000 \
  mcr.microsoft.com/azure-storage/azurite:3.37.0 azurite-blob --blobHost 0.0.0.0
```

After a reboot, run `docker start ptassist-test-storage`. Without Docker, run it with Node.js 22 or newer and leave it open in its own terminal. `--inMemoryPersistence` keeps it from writing files, uploaded videos included, into the current folder (`/.gitignore` ignores those files in case you leave it out):

```bash
npx --yes --package=azurite@3.37.0 azurite-blob --inMemoryPersistence
```

Keep the Azurite version and the `azure-storage-blob` pin in `requirements.txt` in step. Azurite refuses API versions newer than it knows, so a newer SDK alone fails every storage test with "The API version ... is not supported by Azurite". Bump both together, here, in `/compose.yaml`, and in `/.github/workflows/pr-ci.yml`.

Use the `storage` fixture for the app's storage, and `blob_service` (an Azure SDK client) to check what it did:

```python
def test_example(storage) -> None:
    storage.upload("sessions/1.mp4", b"...", "video/mp4")
    response = httpx.get(storage.read_url("sessions/1.mp4"))
```

Tests never call Clerk. `tests/conftest.py` signs tokens with its own key and fakes the SDK's two network calls (fetching Clerk's public keys and looking up a user), so the SDK still checks every token. Use the `client` and `clerk` fixtures:

```python
def test_example(client, clerk) -> None:
    clerk.add_user("user_1", "pat@example.com")  # a Clerk user and their email
    response = client.get("/me", headers=clerk.headers("user_1"))
```

Tests never call the AI service either. The `client` fixture brings in `ai_service`, a fake `POST /analyze` that answers with the example squat result, and TestClient runs an upload's background analysis before `client.post` returns. Change its answer, or make it fail, before the upload:

```python
def test_example(client, clerk, ai_service) -> None:
    ai_service.status_code = 500  # or: ai_service.body = {...}, ai_service.error = httpx.ConnectError("refused")
    ...  # upload; the session ends failed with analysis_unavailable
    assert ai_service.requests[0]["exercise"] == "squat"  # what the job sent
```

Every route needs a test that rejects the wrong role and the wrong owner.

## Pull request CI

The shared workflow in `/.github/workflows/pr-ci.yml` runs on every pull request,
including documentation-only changes, so required checks are never skipped by a
path filter. It provides three API checks:

- `API lint`: ruff lint and formatting checks.
- `API tests`: pytest with Python 3.12 and `requirements-dev.txt`.
- `API image build`: builds `backend/Dockerfile` without pushing an image.

The workflow uses read-only repository permissions and needs no repository secrets
(tests fake Clerk and use Azurite's built-in development account). The `API tests`
job runs two service containers, the same setup as the local tests: `postgres:17` on
port 5433, with `TEST_DATABASE_URL` pointing at it, and
`mcr.microsoft.com/azure-storage/azurite:3.37.0` on port 10000, with
`TEST_STORAGE_CONNECTION_STRING` set to `UseDevelopmentStorage=true`. The job installs
ffmpeg for synthetic upload fixtures and real ffprobe inspection. The Azurite
image has no health check, so a step waits until it answers before pytest starts.
The same workflow also runs the AI service's checks (`AI lint`, `AI tests`, and
`AI image build`), described in `ai/README.md`, and the web app's checks
(`Web lint` and `Web build`), described in `frontend/README.md`.

### Required checks on main

`main` is protected by the `trunk-based` repository ruleset (**Settings > Rules >
Rulesets**), not a classic branch protection rule. It requires a pull request with
1 approving review and allows squash merges only. Its **Require status checks to
pass** rule lists `API lint`, `API tests`, `API image build`, `AI lint`,
`AI tests`, `AI image build`, `Web lint`, and `Web build` from GitHub Actions, so a
failing check blocks merging. Branches do not need to be up to date with `main`
before merging.

Keep the job names stable: the ruleset matches checks by name, so a renamed or
removed job leaves every pull request waiting for a check that never reports. When
a team adds a job to this workflow, a repository admin must also add its name to
the ruleset for it to block merges.
