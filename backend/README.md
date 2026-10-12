# Backend

FastAPI service. It is the only entry point into PTAssist: the frontend talks only to this API, and only this API talks to the database, storage, and AI service.

## Stack

FastAPI, SQLAlchemy, Alembic, PostgreSQL (psycopg 3 driver), Clerk's Python SDK (`clerk-backend-api`), the Azure Blob SDK (`azure-storage-blob`), pytest, ruff. Runtime dependencies in `requirements.txt`; test and lint tools in `requirements-dev.txt`.

## Layout

```
app/
  main.py    Creates the FastAPI app and includes the routers
  config.py  Settings from environment variables
  db.py      SQLAlchemy engine and the get_db session dependency
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

To add a table: create the model in `app/models/`, import it in `app/models/__init__.py` (so autogenerate can see it), then run `alembic revision --autogenerate`. Always read the generated file before committing. New migrations are linted and formatted with ruff automatically. Constraint and index names follow the naming convention in `app/models/base.py`.

## Every request

1. Verify the Clerk token. No valid token means `401`.
2. Load the user from our `User` table. First call from a new user creates them as a patient.
3. Check the role (patient or therapist). Wrong role means `403`.
4. Check ownership: patients see only their own data, therapists see only linked patients. Not yours means `404`.

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

| Table | Holds |
| --- | --- |
| `User` (`users`) | Clerk id, email, role (`patient` or `therapist`), created time |
| `TherapistPatient` | Which therapist is linked to which patient |
| `Exercise` | The exercise library (5 exercises for the proof of concept): its name in the API, such as `squat`, and whether it is done in reps or held (the plank) |
| `Plan` | A therapist's plan for one patient |
| `PlanExercise` | An exercise in a plan, with targets (reps, sets, frequency, or a hold time in seconds for a hold exercise) |
| `Session` | One uploaded video (one set) for a plan exercise, with status |
| `SessionResult` | The analysis result of a finished session, complete or failed (JSONB, see Analysis results) |

Table names are plural snake_case (`users`), and primary keys are UUIDs (see `app/models/user.py`). The schema changes only through Alembic migrations. Never edit the database by hand, and never change a migration after it is merged.

## Session lifecycle

```
upload -> processing -> complete
                     -> failed (with a reason)
```

1. `POST` upload: validate the file (type, size, and length between `MIN_VIDEO_SECONDS` and `MAX_VIDEO_SECONDS` from `app/schemas/analysis_contract.py`, currently 3 seconds to 2 minutes; import them, don't hard-code them), store it, create the `Session` as `processing`. A file that fails these checks gets an HTTP error, and no session is created.
2. A FastAPI background task creates a 15-minute read link and calls the AI service `POST /analyze`.
3. The result is saved to `SessionResult`, and the session's status becomes the result's `status`: `complete` or `failed`.
4. If there is no valid result, the backend saves a failed result itself: `analysis_unavailable` when the AI service could not be reached, answered with an error, or sent a result that does not match the contract, and `analysis_timed_out` when it did not answer in time.
5. Sessions stuck in `processing` too long are also saved as failed, with `analysis_timed_out`.

A session's result is saved once: after a session is `complete` or `failed` it never changes, and a later answer for it is dropped.

The AI service may take up to 3 minutes for a 2-minute clip, counting from a cold start. On Azure, Container Apps ends any HTTP request after 240 seconds, so the timeout in step 2 must be between 3 and 4 minutes (for example 230 seconds). The stuck cutoff in step 5 must be longer than that timeout, so the cleanup never fails a session the background task is still waiting on. See [Clip limits and timing](../docs/analysis-result.md#clip-limits-and-timing).

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
| Patients | `GET/POST/DELETE /therapist/patients` | Therapist |
| Plans | `POST/PUT /plans`, `GET /plans/me` | Therapist, patient |
| Sessions | `POST /sessions`, `GET /sessions/{id}`, `GET /sessions` | Patient (therapist can read linked patients') |
| Progress | `GET /patients/{id}/progress` | Therapist |

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

Read from environment variables (see `/.env.example`): database URL, Clerk settings, storage settings, and the AI service URL. No secrets in code. Settings are defined in `app/config.py`. Add new ones there and in `/.env.example`.

| Variable | Read by | What |
| --- | --- | --- |
| `DATABASE_URL` | API, Alembic | Postgres URL. Must use the `postgresql+psycopg://` scheme so SQLAlchemy picks the psycopg 3 driver |
| `CLERK_SECRET_KEY` | API | Clerk secret key, to check tokens and look up new users' emails. Secret. See Clerk settings |
| `CLERK_AUTHORIZED_PARTIES` | API | Web app origins, comma-separated. Tokens must come from one of them, and browsers may call the API only from them (CORS). Empty skips the token's origin check and blocks every browser, so set it everywhere |
| `STORAGE_CONNECTION_STRING` | API | Storage account to use. `UseDevelopmentStorage=true` locally (Azurite on `127.0.0.1:10000`). In Azure, the storage account's connection string: it holds the account key, so it is a secret. See Storage |
| `STORAGE_CONTAINER` | API | Private blob container for videos. Default `videos`. Created if missing |
| `TEST_DATABASE_URL` | pytest | The test database. See Testing |
| `TEST_STORAGE_CONNECTION_STRING` | pytest | The test storage, by default `UseDevelopmentStorage=true`. See Testing |
| `AZURITE_ACCOUNT_KEY` | Docker Compose | Azurite's well-known key, for the `api` service's connection string. Not read by the API itself. See Storage in Docker Compose |

Alembic only needs `DATABASE_URL`. Without `CLERK_SECRET_KEY` the API still starts (and logs a warning about it), but every route that needs sign-in fails with `500` and a `detail` that names the missing key (the web app shows it). Without `STORAGE_CONNECTION_STRING` it also starts, but anything that uses storage fails with `500`.

A connection string contains `;`, so in `/.env` wrap any value other than `UseDevelopmentStorage=true` in double quotes, or `source` splits it.

## Testing

pytest, against a real Postgres database: `TEST_DATABASE_URL`, by default `postgresql+psycopg://ptassist:ptassist@localhost:5433/ptassist_test`. Tests always use it in place of `DATABASE_URL`. Each run builds the schema with `alembic upgrade head`, empties the tables before every test, and drops everything at the end with `alembic downgrade base`, so every run also checks that the migrations work both ways. Never point it at a database you want to keep.

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
`TEST_STORAGE_CONNECTION_STRING` set to `UseDevelopmentStorage=true`. The Azurite
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
