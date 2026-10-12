# Analysis result

The result of analyzing one exercise video: the rep count (or hold time), form score, details for each rep, feedback for the patient, and the reason if the analysis failed. Three parts of PTAssist use it:

- The **AI service** makes it: `POST /analyze` returns it.
- The **backend** checks it, saves it, and records its own failures in the same shape.
- The **frontend** shows it, using types generated from the backend's API (Orval) once an API route returns it (SCRUM-64).

This contract was set in SCRUM-28. The [decisions](#decisions) behind it, and how to change each one, are at the end of this page.

## Where it is defined

| File | What it is |
| --- | --- |
| `ai/app/analysis_contract.py` | The contract. The AI service owns it. **Edit this one** |
| `backend/app/schemas/analysis_contract.py` | An exact copy for the backend. **Never edit it by hand** |
| `docs/analysis-result-examples/` | Example results, one for each kind of result |

The AI service and the backend run in separate containers, so the backend cannot import code from `ai/`. It keeps a copy instead. For the same reason, **the contract file may import only the Python standard library and pydantic**: the backend's copy cannot see the AI service's other code or libraries (NumPy, OpenCV, MediaPipe). The contract file holds everything the two services must agree on: the request (`AnalyzeRequest`), the result (`AnalysisResult`), the error codes and their messages, and the clip length limits.

To change the contract:

1. Edit `ai/app/analysis_contract.py`, following the rules in [Changing the contract](#changing-the-contract).
2. Copy it to the backend, from the repo root:
   ```bash
   cp ai/app/analysis_contract.py backend/app/schemas/analysis_contract.py
   ```
3. Update this page and the examples in the same pull request.

**The copy check.** `ai/tests/test_analysis_contract.py` and `backend/tests/test_analysis_contract.py` each compare the two files and fail if they differ. They run in the `AI tests` and `API tests` checks, which must both pass before a pull request can merge, so a change to only one side cannot reach `main`. Both test suites also load every example file.

Only the AI service's lint (ruff) checks the contract file. The backend's lint skips its copy (`extend-exclude` in `backend/pyproject.toml`), so the two services' lint settings can differ without breaking the copy check.

## The result

`docs/analysis-result-examples/squat.json`, shortened to one rep:

```json
{
  "status": "complete",
  "rep_count": 1,
  "hold_seconds": null,
  "form_score": 70,
  "reps": [
    {
      "index": 1,
      "start_seconds": 4.4,
      "end_seconds": 7.0,
      "side": null,
      "score": 70,
      "issues": [{ "code": "knees_cave_in", "message": "Your knees moved inward." }],
      "metrics": { "min_knee_angle_degrees": 95.0 }
    }
  ],
  "feedback": ["Push your knees out so they stay over your toes."],
  "error_code": null,
  "error_message": null,
  "analyzer_version": "0.1.0"
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `status` | `"complete"` or `"failed"` | Whether the video was analyzed |
| `rep_count` | integer or null | Reps counted, for [exercises done in reps](#reps-and-holds). `0` means the video was fine but no full rep was seen. Null for hold exercises and failed results |
| `hold_seconds` | number or null | The longest unbroken hold in seconds, for hold exercises (the plank). Null for exercises done in reps and failed results |
| `form_score` | integer 0 to 100, or null | Overall form score (see [Scoring](#scoring)). Null when there are no reps or holds, and for failed results |
| `reps` | list | One entry per rep, or per unbroken hold, in the order they started. Empty if none |
| `feedback` | list of strings | Up to 3 tips for the patient, most important first (see [Feedback](#feedback)). Empty for failed results |
| `error_code` | string or null | Why the analysis failed (see [Failures](#failures)). Null when complete |
| `error_message` | string or null | What the patient sees when it failed. Null when complete |
| `analyzer_version` | string or null | The version of the analysis code that made the result, such as `"0.1.0"` (see [Versions](#versions)). Null only when the backend recorded the failure itself (`analysis_unavailable` or `analysis_timed_out`) |

Each entry in `reps`:

| Field | Type | Meaning |
| --- | --- | --- |
| `index` | integer, 1 or more | 1, 2, 3, ... in the order the reps started |
| `start_seconds`, `end_seconds` | number | When the rep (or hold) started and ended, in seconds from the start of the video |
| `side` | `"left"`, `"right"`, `"both"`, or null | Which side of the body did the rep (see [Sides](#sides)) |
| `score` | integer 0 to 100 | Form score for this rep (see [Scoring](#scoring)) |
| `issues` | list of `{code, message}` | Form problems seen during this rep. `code` is a short snake_case name such as `knees_cave_in`. `message` says what went wrong, in plain language. Empty if none |
| `metrics` | object, name to number | Extra measurements for this exercise, such as `min_knee_angle_degrees`. Each exercise's spec lists its own, and each name ends with its unit. Empty if none |

### Rules every result follows

The contract rejects a result whose fields contradict each other, so the frontend can rely on these rules:

- A failed result has an `error_code` and an `error_message`, and no `rep_count`, `hold_seconds`, `form_score`, `reps`, or `feedback`.
- A complete result has no `error_code` or `error_message`, has an `analyzer_version`, and sets exactly one of `rep_count` and `hold_seconds`.
- `rep_count` equals the number of entries in `reps`.
- `hold_seconds` equals the longest entry in `reps` (end minus start), or 0 when `reps` is empty. Round times and `hold_seconds` to 0.1 seconds, or not at all: the check allows 0.2 seconds of difference for that rounding.
- `reps` are listed and numbered 1, 2, 3, ... in the order they started, and no rep ends before it starts. Reps may overlap in time (for example the left and right arm); that is not checked.
- `form_score` is null exactly when `reps` is empty.
- No number is NaN or infinite. JSON cannot hold them, so they are rejected when the result is built.

### Showing a result

- `status` is `"failed"`: show `error_message`, and offer a re-upload unless `error_code` is `unknown_exercise` (uploading again would fail the same way).
- `hold_seconds` is not null: show the hold time. It can be `0`, so check for null, not for a true value. Otherwise, show `rep_count`.
- Color `form_score` and each rep's `score` by [band](#scoring).

## Reps and holds

Most exercises are done in reps. The plank is held for time, so it has no reps.

- An exercise done in reps sets `rep_count`, and `hold_seconds` is null.
- A hold exercise sets `hold_seconds`, and `rep_count` is null.
- For a hold, each unbroken hold is one entry in `reps`, with its own start and end, score, and issues. A plank where the patient drops to their knees once and starts again has two entries (see `plank.json`).
- `hold_seconds` is the **longest** unbroken hold, not the total. A therapist prescribes a hold time ("hold for 30 seconds"), and the longest hold is what compares to it. The total is the sum of the entries' durations.
- A hold ends only when the patient leaves the position, for example by dropping to their knees or standing up. Poor form during the hold, such as sagging hips, is an issue inside that hold, not a break. The exact thresholds belong in the plank's spec.
- If no hold is seen, the result is complete with `hold_seconds: 0`, no entries in `reps`, and `form_score: null`, like zero reps (see `plank-no-hold.json`).

Whether an exercise is done in reps or held is not part of the contract. Today only the plank is a hold. The AI service knows it from its analyzers. The backend's `Exercise` table will need a field for it, because a plank's plan target is a time in seconds, not reps and sets (SCRUM-43).

**One video is one set.** Reps have no set number, so a plan of "3 sets of 30-second planks" means 3 uploads. If we later want several sets in one video, we can add an optional `set` field to each rep (an allowed change, see [Changing the contract](#changing-the-contract)).

## Sides

`side` says which side of the body did a rep:

| Value | When |
| --- | --- |
| `"left"`, `"right"` | One side at a time, such as a side leg raise |
| `"both"` | Both sides at once, such as raising both arms in a shoulder abduction |
| `null` | Sides do not apply, such as a squat, plank, or cat-cow |

The analyzer decides the side from which limb moved. `rep_count` is the total for both sides. To count each side, count the entries in `reps` (see `side-leg-raise.json`).

## Failures

When a video cannot be analyzed, the AI service still answers `200`, with `status: "failed"`, an `error_code`, and an `error_message`. (A request that does not match `AnalyzeRequest` gets `422`. The backend records any other error status, such as a 500 from a crash, as `analysis_unavailable`; see Catching crashes below.) When the backend has no valid result, it records a failure in the same shape.

Every code and its patient message is in `ERROR_MESSAGES` in the contract file, so the AI service and the backend use the same wording. `AnalysisResult.failed(error_code, analyzer_version)` builds a failed result with the right message.

| Code | Recorded by | When |
| --- | --- | --- |
| `video_unreadable` | AI service | The downloaded file is damaged or is not a video |
| `too_short` | AI service | The video is shorter than 3 seconds |
| `too_long` | AI service | The video is longer than 2 minutes |
| `no_person` | AI service | Nobody was found in the video |
| `multiple_people` | AI service | More than one person was found in the video |
| `unknown_exercise` | AI service | The AI service has no analyzer for this exercise name |
| `analysis_error` | AI service | Our code crashed (a bug), or the video could not be downloaded from storage |
| `analysis_unavailable` | Backend | The AI service could not be reached, answered with an error, or sent a result that does not match the contract |
| `analysis_timed_out` | Backend | No result arrived in time, including sessions stuck in `processing` |

- **Zero reps is not a failure.** If the video is fine but no full rep was seen, the result is complete with `rep_count: 0`.
- **Rejected uploads are not failures either.** A file that is the wrong type, too large, shorter than 3 seconds, or longer than 2 minutes is refused by the upload endpoint with an HTTP error (SCRUM-44), before any session or result exists. The AI service's `too_short` and `too_long` codes are a backstop for a clip the upload check could not measure.
- **Catching crashes:** the real pipeline (Sprint 2) will catch a failed download or an unexpected error and return `analysis_error`. Until then, a crash in the AI service is an HTTP 500, which the backend records as `analysis_unavailable`.

## Clip limits and timing

- **Clips are 3 seconds to 2 minutes** (`MIN_VIDEO_SECONDS` and `MAX_VIDEO_SECONDS` in the contract file). Two minutes leaves time for older or injured patients, who may move slowly. The upload endpoint will import these constants to check the same limits before storing a video (SCRUM-44), and the AI service will check them again (SCRUM-73). Never copy the numbers into other code.
- **Performance target:** a 2-minute clip analyzed in 3 minutes or less on Azure (SCRUM-74), counting from a cold start: starting the AI container from zero and downloading the video are part of the 3 minutes.
- **Upper limit for the backend's call to the AI service:** the backend waits for `POST /analyze` in one HTTP request, and on Azure, Container Apps ends any HTTP request after 240 seconds (4 minutes). So the backend's call timeout (SCRUM-45) must be between 3 and 4 minutes, for example 230 seconds. Then the backend records `analysis_timed_out` itself before Azure cuts the call.
- **Everything else that waits must wait longer, in this order:** the backend's call timeout (SCRUM-45) < the cutoff for sessions stuck in `processing` (SCRUM-66) ≤ the frontend's polling timeout (SCRUM-57). The stuck cutoff must be longer than the call timeout, so the cleanup never fails a session the background task is still waiting on. The frontend should not give up before the backend does. These two are not limited by Azure, because neither waits on one request.
- **If 2-minute clips don't fit:** if SCRUM-74 finds a 2-minute clip cannot be analyzed in time on Azure, lower `MAX_VIDEO_SECONDS`, or ask the team before changing how the backend hands off the work (a job queue is a Spring stretch goal).
- **File size:** a 2-minute phone video can be a few hundred MB, more at 4K. The upload size limit is set in SCRUM-44.

## Scoring

The rules below are the spec for the shared analysis framework, built in SCRUM-50 (Sprint 2). Until then, the stub in `ai/app/main.py` returns hand-made scores and feedback that follow them.

The framework computes every score the same way. Each exercise's analyzer only reports issues. This keeps scores comparable across exercises on the progress chart, and every point lost can be explained to a therapist ("−30 because your knees moved inward").

- Each issue code has a penalty, set in the exercise's spec. For example, a major problem costs 30 points and a minor one 10.
- **Rep score** = 100 minus the penalties of the issues in that rep, never below 0. Each issue counts once per rep.
- **Overall `form_score`** = the average of the rep scores.
- **Hold score** = the share of the hold's time spent in good form, from 0 to 100. For example, 17 good seconds out of 22 scores 77.
- **Overall `form_score` for holds** = all good-form seconds divided by all hold seconds, from 0 to 100. Longer holds count more.
- **Rounding:** every score is a whole number. Round to the nearest one, with exact halves rounding up (86.5 becomes 87). Python's `round()` does not do this (it turns 86.5 into 86), so use `math.floor(x + 0.5)`.

Score bands, so every screen colors scores the same way:

| Score | Band |
| --- | --- |
| 80 to 100 | Good |
| 50 to 79 | Fair |
| 0 to 49 | Needs work |

## Feedback

`feedback` is the short summary at the top of the results screen: what to do next time. It is separate from the issues in `reps`, which say what went wrong in each rep.

- The framework builds it from the issues. It ranks each issue code by how many reps had it times its penalty, because an issue seen on many reps, or a costly one, matters most. It keeps the top 3. SCRUM-50 may refine this, including how ties are ordered.
- Each issue code has a tip in the exercise's spec, and the tip is the feedback line. For example, the issue `knees_cave_in` ("Your knees moved inward.") has the tip "Push your knees out so they stay over your toes."
- The framework also writes two lines itself. Each is the same sentence for every exercise:
  - With no issues: "Great form. Keep it up."
  - With no reps or holds at all: "We didn't see a full rep or hold. Keep your whole body in the frame and finish each one." (see `squat-zero-reps.json` and `plank-no-hold.json`). A result with nothing to score also has no issues, so it needs its own line instead of the positive one.
- Plain language and no medical claims. The wording is reviewed in SCRUM-90. Patients and therapists see the same text.

So for each issue code, an exercise's spec lists: the code, the message (what went wrong), the tip (what to do), and the penalty.

## Exercise names

| Exercise | Name in the API | Kind |
| --- | --- | --- |
| Plank | `plank` | Hold |
| Arm or shoulder abduction | `shoulder_abduction` | Reps |
| Side leg raise | `side_leg_raise` | Reps |
| Squat | `squat` | Reps |
| Cat-cow ("cat and dog") | `cat_cow` | Reps |

These are the five exercises proposed to the sponsor (SCRUM-42). `exercise` in the request is a plain string, not a fixed list, so adding, removing, or renaming an exercise does not change the contract. The names live in two places:

- The AI service: its analyzers in `ai/app/analysis/exercises/`. Until those exist, `HOLD_EXERCISES` and `REP_EXERCISES` in `ai/app/main.py`.
- The backend: the `Exercise` table (SCRUM-43), in a text column rather than a database enum, so changing the list adds or changes rows, not the table's structure.

An unknown name fails with `unknown_exercise`. Adding or renaming an exercise changes a row in the `Exercise` table, which is done only with a new Alembic migration, never by hand (ask the backend team). The AI service's name must change at the same time. Whether a rename also affects saved sessions depends on the data model in SCRUM-43.

## Versions

`analyzer_version` records which version of the analysis code made a result. When an exercise is tuned (Sprint 4), a score of 75 before and after may not mean the same thing. The version tells them apart, for the evaluation report and to explain jumps on the progress chart.

- There is one version for the whole AI service: `ANALYZER_VERSION` in `ai/app/main.py`, in the form `0.1.0`.
- Raise it whenever anything that can change a result changes: an exercise's analyzer or thresholds, the shared framework (penalties, scoring, feedback, rep splitting), or the keypoint step (MediaPipe or video normalization). The stub uses `0.1.0-stub`.
- It is null only for failures the backend records itself (`analysis_unavailable`, `analysis_timed_out`), because the backend has no valid result from the AI service. A complete result always has one.

## Changing the contract

Results are saved in the database and kept, so a result saved before a change must still load after it. There is no version number for the shape of the result. Instead:

- **Only add fields, and give each new field a default value** (such as `None` or an empty list), so older results still load.
- **Do not rename or remove fields, or change their types.** If that is ever unavoidable, the same pull request needs an Alembic migration that rewrites the saved results.
- **Adding an error code is fine:** add it to `ErrorCode` and `ERROR_MESSAGES` (a test checks every code has a message). Removing or renaming a code needs the migration.
- **New validation rules** must still accept every result already saved.
- Then copy the file to the backend, update this page and the examples, and, once the API returns results (SCRUM-64), regenerate the frontend's Orval hooks.

## How the backend stores it

The backend builds this in SCRUM-43 (tables) and SCRUM-45 (calling the AI service).

- Every finished session gets one `SessionResult` row holding this JSON, whether it completed or failed. The failure reason lives there, not on `Session`.
- A session's result is saved once. After a session is `complete` or `failed`, it never changes, and a later answer for it is dropped (how is decided in SCRUM-45 and SCRUM-66).
- When the backend has no valid result (the AI service is down or answers with an error, the call times out, the answer does not match the contract, or the session is stuck), it saves a failed result itself with `AnalysisResult.failed(...)` and `analyzer_version=None`.
- `Session.status` (`processing`, `complete`, or `failed`) is what the frontend polls. Once it is `complete` or `failed`, the `SessionResult` has the details.
- The whole result is stored in one JSONB column, with no separate columns for `rep_count` or `form_score`. Postgres can still read fields inside it (for example `result->>'form_score'` for the progress chart). If a query ever needs it, a migration can add real columns.
- The backend checks every result from the AI service against the contract before saving it. An answer that does not match is a bug, so the session is saved as failed with `analysis_unavailable` instead.

## Examples

`docs/analysis-result-examples/` has one file for each kind of result. Codes, messages, tips, metrics, and numbers in the example files are placeholders until the exercise specs (SCRUM-29) are written. The frontend can use them as test data until the API returns real results (SCRUM-64). The result view (SCRUM-59) is built before any API route returns this result, so Orval has no `AnalysisResult` type yet. Until then, write a temporary TypeScript type from the field tables on this page, outside the generated `src/api/` folder, and delete it once a route returns the result and the Orval hooks are regenerated.

| File | Shows |
| --- | --- |
| `squat.json` | An exercise done in reps, with issues, metrics, and feedback |
| `squat-zero-reps.json` | A complete result with no reps counted |
| `side-leg-raise.json` | Reps on the left and right sides |
| `plank.json` | A hold exercise with two unbroken holds |
| `plank-no-hold.json` | A complete result for a hold exercise with no hold seen (`hold_seconds` is 0) |
| `failed-no-person.json` | A failure reported by the AI service |
| `failed-timed-out.json` | A failure recorded by the backend (`analyzer_version` is null) |

## Decisions

Decided in SCRUM-28 (October 2026). Each one says why, and what to change if we change our minds.

1. **Failure reasons are a fixed list of codes, each with a patient message, all in the contract file.** The list includes the backend's own failures. *Why:* the frontend can react to the reason where it matters (for example, no re-upload for `unknown_exercise`) and needs one list, and one place keeps the wording consistent. *To change:* edit `ErrorCode` and `ERROR_MESSAGES`.
2. **Clips are 3 seconds to 2 minutes.** *Why:* older or injured patients may move slowly, and under 3 seconds cannot hold a full rep. *To change:* edit `MIN_VIDEO_SECONDS` or `MAX_VIDEO_SECONDS`. The messages and the upload and AI checks use these constants, but re-read the `too_short` and `too_long` messages, and update the docs that state the limits (this page's Failures and Clip limits sections, the `ai/README.md` Limits section, and the `backend/README.md` Session lifecycle). Then revisit the performance target and the timeouts in [Clip limits and timing](#clip-limits-and-timing).
3. **Zero reps is a complete result with `rep_count: 0`, not a failure.** *Why:* the video was fine; the patient just did not finish a rep. *To change:* add a `no_reps` error code (an allowed change) and have the framework (SCRUM-50) fail instead of returning 0. Results already saved with `rep_count: 0` can stay as they are.
4. **Issues carry a readable message, and issue codes are open strings.** *Why:* the frontend can show an issue without a lookup table, and a new form check does not change the contract. *To change:* restricting codes to a fixed list would be a breaking change.
5. **Each rep has start and end times and optional metrics.** *Why:* times give rep durations for tempo checks, let the evaluation (SCRUM-72) compare each rep to labeled clips, give hold durations, and fit reporting reps live later. Metrics hold exercise-specific numbers such as range of motion. *To change:* new per-rep fields and new metric names are allowed changes. Removing or renaming `start_seconds` or `end_seconds` needs a migration.
6. **The framework scores every exercise the same way; analyzers only report issues.** *Why:* scores stay comparable across exercises and explainable to a therapist. *To change:* penalties are in each exercise's spec; the formula is in the framework (SCRUM-50).
7. **Feedback is up to 3 tips, built from the issues.** *Why:* one short summary to act on, while the issues keep the detail. *To change:* the limit and ranking live in the framework, not the contract.
8. **Exercise names are plain strings, not a fixed list.** *Why:* the sponsor has not confirmed the exercises yet (SCRUM-42), so changing them must stay cheap. *To change:* see [Exercise names](#exercise-names).
9. **Only `analyzer_version`; no version number for the shape.** *Why:* a shape version would need code to convert old results. Additive-only changes avoid that. *To change:* add an optional `schema_version` field, which is itself an allowed change.
10. **The AI service owns the contract, and the backend keeps an exact copy that a test checks.** *Why:* the backend needs the shape to check results, record its own failures, and give the frontend types, but it cannot import from `ai/`. Sharing one file would mean building the API image from the repo root, and working around both services' code being named `app`. *To change:* if the copy becomes a burden, move the file into a small package that both services install.
11. **Every finished session has a `SessionResult`, including failed ones, and the failure reason lives there.** *Why:* one place to look for what happened to a session. *To change:* moving the failure reason onto `Session` needs a migration, and the results endpoints (SCRUM-64) and the frontend would then read it from there.
12. **Results are stored only as JSONB.** *Why:* simple, and fast enough at proof-of-concept size. *To change:* add columns with a migration.
13. **Holds set `hold_seconds` (the longest unbroken hold), each hold is an entry in `reps`, reps record their `side`, and one video is one set.** *Why:* the plank has no reps, therapists prescribe hold times, and differences between sides matter in physical therapy. *To change:* see [Reps and holds](#reps-and-holds). Adding a `set` field later is an allowed change.
