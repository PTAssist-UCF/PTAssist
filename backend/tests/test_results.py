"""Tests for a patient's sessions, a session's result, and progress (routes/results.py).

Sessions and results are saved straight to the database, using the example results in
docs/analysis-result-examples/, so no video or AI service is needed.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.db import engine
from app.main import app
from app.models import (
    Exercise,
    ExerciseKind,
    ExerciseSession,
    Plan,
    PlanExercise,
    Role,
    SessionResult,
    SessionStatus,
    TherapistPatient,
    User,
)
from app.schemas.analysis_contract import AnalysisResult

EXAMPLES = Path(__file__).parents[2] / "docs" / "analysis-result-examples"

# pat's sessions: a label, the exercise, the day in November 2026 it was uploaded, and
# the example result it got (None: still processing).
HISTORY = [
    ("squat_1", "squat", 1, "squat"),
    ("plank_1", "plank", 2, "plank"),
    ("squat_2", "squat", 3, "failed-no-person"),
    ("plank_2", "plank", 4, "failed-timed-out"),
    ("squat_3", "squat", 5, "squat-zero-reps"),
    ("plank_3", "plank", 6, "plank-no-hold"),
    ("leg_1", "side_leg_raise", 8, None),
    ("squat_4", "squat", 9, None),
]
EXERCISE_OF = {label: exercise for label, exercise, _, _ in HISTORY}

ROUTES = {
    "sessions": "/patients/{patient_id}/sessions",
    "result": "/sessions/{session_id}/result",
    "progress": "/patients/{patient_id}/progress",
}


def day(number: int) -> datetime:
    """9 AM UTC on that day of November 2026."""
    return datetime(2026, 11, number, 9, tzinfo=UTC)


def example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def add_plan(db: Session, therapist: User, patient: User) -> dict[str, PlanExercise]:
    """A plan with every exercise in the library. Returns its exercises by name."""
    plan = Plan(therapist_id=therapist.id, patient_id=patient.id)
    targets = {}
    for exercise in db.scalars(select(Exercise)):
        if exercise.kind == ExerciseKind.HOLD:
            target = {"hold_seconds": 30}
        else:
            target = {"reps": 10}
        targets[exercise.name] = PlanExercise(
            plan=plan, exercise=exercise, sets=3, times_per_week=3, **target
        )
    db.add(plan)
    db.commit()
    return targets


def add_session(
    db: Session, target: PlanExercise, on: int, result: str | None
) -> uuid.UUID:
    """A session uploaded on that day, finished with that example result (complete or
    failed, as the result says), or still processing without one."""
    saved = None if result is None else example(result)
    session = ExerciseSession(
        plan_exercise=target,
        status=SessionStatus.PROCESSING if saved is None else saved["status"],
        video_key=f"sessions/{uuid.uuid4()}.mp4",
        created_at=day(on),
    )
    if saved is not None:
        session.result = SessionResult(result=saved)
    db.add(session)
    db.commit()
    return session.id


@pytest.fixture
def users(db: Session) -> dict[str, User]:
    """Two patients and two therapists. ther is linked to pat, and other_ther only to
    other_pat. A user's Clerk id is user_<name>."""
    users = {
        name: User(clerk_id=f"user_{name}", email=f"{name}@example.com", role=role)
        for name, role in [
            ("pat", Role.PATIENT),
            ("other_pat", Role.PATIENT),
            ("ther", Role.THERAPIST),
            ("other_ther", Role.THERAPIST),
        ]
    }
    db.add_all(users.values())
    db.flush()
    for therapist, patient in [("ther", "pat"), ("other_ther", "other_pat")]:
        db.add(
            TherapistPatient(
                therapist_id=users[therapist].id, patient_id=users[patient].id
            )
        )
    db.commit()
    return users


@pytest.fixture
def history(db: Session, users: dict[str, User]) -> dict[str, uuid.UUID]:
    """The ids of pat's sessions in HISTORY, and of one of other_pat's, by label."""
    targets = add_plan(db, users["ther"], users["pat"])
    ids = {
        label: add_session(db, targets[exercise], on, result)
        for label, exercise, on, result in HISTORY
    }
    other_targets = add_plan(db, users["other_ther"], users["other_pat"])
    ids["other"] = add_session(db, other_targets["squat"], 7, "squat")
    return ids


def get(client, clerk, user: str, route: str, patient_id, session_id):
    """GET one of ROUTES as user_<user>, about this patient (or this session)."""
    path = ROUTES[route].format(patient_id=patient_id, session_id=session_id)
    return client.get(path, headers=clerk.headers(f"user_{user}"))


# GET /patients/{patient_id}/sessions


@pytest.mark.parametrize("user", ["pat", "ther"])
def test_sessions_are_listed_newest_first(
    client, clerk, db, users, history, user
) -> None:
    """The patient and their linked therapist see the same list: every status, but
    never another patient's sessions."""
    response = get(client, clerk, user, "sessions", users["pat"].id, None)

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [
        str(history[label]) for label, _, _, _ in reversed(HISTORY)
    ]
    assert [datetime.fromisoformat(item["created_at"]) for item in body] == [
        day(on) for _, _, on, _ in reversed(HISTORY)
    ]
    assert [item["status"] for item in body] == [
        "processing",
        "processing",
        "complete",
        "complete",
        "failed",
        "failed",
        "complete",
        "complete",
    ]
    oldest = body[-1]  # squat_1
    assert set(oldest) == {
        "id",
        "plan_exercise_id",
        "exercise_name",
        "exercise_display_name",
        "status",
        "created_at",
    }
    session = db.get(ExerciseSession, history["squat_1"])
    assert oldest["plan_exercise_id"] == str(session.plan_exercise_id)
    assert (oldest["exercise_name"], oldest["exercise_display_name"]) == (
        "squat",
        "Squat",
    )
    assert body[1]["exercise_display_name"] == "Side-lying leg raise"  # leg_1


def test_a_patient_without_sessions_gets_empty_lists(client, clerk, users) -> None:
    for route in ["sessions", "progress"]:
        response = get(client, clerk, "pat", route, users["pat"].id, None)

        assert response.status_code == 200
        assert response.json() == []


# GET /sessions/{session_id}/result


@pytest.mark.parametrize("user", ["pat", "ther"])
@pytest.mark.parametrize(
    ("label", "status", "result"),
    [
        ("squat_1", "complete", "squat"),
        ("plank_1", "complete", "plank"),
        ("squat_2", "failed", "failed-no-person"),
        ("plank_2", "failed", "failed-timed-out"),
        ("squat_4", "processing", None),
    ],
)
def test_result_is_the_saved_analysis_result(
    client, clerk, users, history, user, label, status, result
) -> None:
    """Exactly as saved, for the patient and their linked therapist. A failed one has
    the reason. A processing one has no result yet."""
    response = get(client, clerk, user, "result", None, history[label])

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(history[label])
    assert body["status"] == status
    assert body["exercise_name"] == EXERCISE_OF[label]
    assert body["result"] == (None if result is None else example(result))


def test_status_and_result_are_read_together(client, clerk, users, history) -> None:
    """The analysis job can save a result at any moment, also while this route reads
    the session. The answer must then be the session before (processing, no result)
    or after (complete, with it), never processing with a result. Here the job saves
    right after the route's first query on the sessions table."""
    session_id = history["squat_4"]  # processing
    saved = []

    def job_saves_now(conn, cursor, statement, parameters, context, executemany):
        if saved or "FROM sessions" not in statement:
            return
        saved.append(session_id)  # first, so the job's own queries return above
        # As the job does (app/jobs/analysis.py): the status and the result together.
        with Session(engine) as job, job.begin():
            job.get(ExerciseSession, session_id).status = SessionStatus.COMPLETE
            job.add(SessionResult(session_id=session_id, result=example("squat")))

    event.listen(engine, "after_cursor_execute", job_saves_now)
    try:
        response = get(client, clerk, "pat", "result", None, session_id)
    finally:
        event.remove(engine, "after_cursor_execute", job_saves_now)

    assert saved == [session_id]  # the job saved during the request
    body = response.json()
    # Before the save or after it, never half of each. (With this route's single
    # query, it is before.)
    assert (body["status"], body["result"]) in [
        ("processing", None),
        ("complete", example("squat")),
    ]
    after = get(client, clerk, "pat", "result", None, session_id).json()
    assert (after["status"], after["result"]) == ("complete", example("squat"))


def test_result_has_the_same_fields_as_the_list(client, clerk, users, history) -> None:
    listed = get(client, clerk, "pat", "sessions", users["pat"].id, None)
    response = get(client, clerk, "pat", "result", None, history["squat_1"])

    body = response.json()
    assert body.pop("result") == example("squat")
    assert body == listed.json()[-1]


# GET /patients/{patient_id}/progress


def point(session_id: uuid.UUID, on: int, result: str) -> dict[str, Any]:
    """The progress point expected for a session with that example result."""
    saved = example(result)
    return {
        "session_id": str(session_id),
        "created_at": day(on),
        "form_score": saved["form_score"],
        "rep_count": saved["rep_count"],
        "hold_seconds": saved["hold_seconds"],
        "analyzer_version": saved["analyzer_version"],
    }


def parsed(progress: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The progress with each point's created_at read as a time, to compare."""
    for exercise in progress:
        for item in exercise["sessions"]:
            item["created_at"] = datetime.fromisoformat(item["created_at"])
    return progress


@pytest.mark.parametrize("user", ["pat", "ther"])
def test_progress_charts_complete_sessions_per_exercise(
    client, clerk, users, history, user
) -> None:
    """Only complete sessions, oldest first, by exercise name. Failed and processing
    sessions are left out, and so is side_leg_raise, which has no complete one. A
    complete session with no rep or hold seen is a point without a form_score."""
    response = get(client, clerk, user, "progress", users["pat"].id, None)

    assert response.status_code == 200
    assert parsed(response.json()) == [
        {
            "exercise_name": "plank",
            "exercise_display_name": "Plank",
            "exercise_kind": "hold",
            "sessions": [
                point(history["plank_1"], 2, "plank"),
                point(history["plank_3"], 6, "plank-no-hold"),
            ],
        },
        {
            "exercise_name": "squat",
            "exercise_display_name": "Squat",
            "exercise_kind": "reps",
            "sessions": [
                point(history["squat_1"], 1, "squat"),
                point(history["squat_3"], 5, "squat-zero-reps"),
            ],
        },
    ]


def test_progress_has_the_numbers_a_chart_needs(client, clerk, users, history) -> None:
    """Spelled out once: a hold time for the plank, reps for the squat."""
    response = get(client, clerk, "pat", "progress", users["pat"].id, None)

    plank, squat = response.json()
    good_hold, no_hold = plank["sessions"]
    assert (good_hold["form_score"], good_hold["hold_seconds"]) == (86, 22.0)
    assert good_hold["rep_count"] is None
    assert (no_hold["form_score"], no_hold["hold_seconds"]) == (None, 0.0)
    three_reps, zero_reps = squat["sessions"]
    assert (three_reps["form_score"], three_reps["rep_count"]) == (87, 3)
    assert three_reps["hold_seconds"] is None
    assert (zero_reps["form_score"], zero_reps["rep_count"]) == (None, 0)
    assert three_reps["analyzer_version"] == "0.1.0"


def test_progress_joins_an_exercise_from_several_plans(
    client, clerk, db, users, history
) -> None:
    """Progress is per exercise, not per plan: a squat in a second plan (here from
    another therapist) is on the same line, in time order."""
    second_plan = add_plan(db, users["other_ther"], users["pat"])
    later = add_session(db, second_plan["squat"], 4, "squat")

    response = get(client, clerk, "ther", "progress", users["pat"].id, None)

    squat = response.json()[1]
    assert [item["session_id"] for item in squat["sessions"]] == [
        str(history["squat_1"]),
        str(later),
        str(history["squat_3"]),
    ]


def test_progress_skips_a_complete_session_without_a_result(
    client, clerk, db, users, history
) -> None:
    """The job saves the result and the status together, so this can't happen. If it
    did, the chart would skip the session instead of failing."""
    session = db.get(ExerciseSession, history["squat_4"])
    session.status = SessionStatus.COMPLETE  # still no result
    db.commit()

    response = get(client, clerk, "pat", "progress", users["pat"].id, None)

    assert response.status_code == 200
    squat = response.json()[1]
    assert str(history["squat_4"]) not in [p["session_id"] for p in squat["sessions"]]


# Permissions, for every route


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("user", ["other_pat", "other_ther"])
def test_another_patient_or_an_unlinked_therapist_gets_404(
    client, clerk, users, history, route, user
) -> None:
    """Wrong owner: the same 404 as for an id that doesn't exist, so the answer doesn't
    tell whether the patient or the session exists."""
    response = get(client, clerk, user, route, users["pat"].id, history["squat_1"])
    unknown = get(client, clerk, user, route, uuid.uuid4(), uuid.uuid4())

    assert (response.status_code, unknown.status_code) == (404, 404)
    assert response.json() == unknown.json()


@pytest.mark.parametrize("route", ROUTES)
def test_a_patient_cannot_see_through_a_leftover_link(
    client, clerk, db, users, history, route
) -> None:
    """Wrong role: the role decides, not the link. A therapist made a patient again
    keeps their links (app/promote_therapist.py --demote --force), but sees none of
    those patients."""
    ids = users["pat"].id, history["squat_1"]
    assert get(client, clerk, "ther", route, *ids).status_code == 200
    users["ther"].role = Role.PATIENT
    db.commit()

    response = get(client, clerk, "ther", route, *ids)

    assert response.status_code == 404


@pytest.mark.parametrize("route", ROUTES)
def test_a_therapist_cannot_see_their_own_patient_data(
    client, clerk, db, users, history, route
) -> None:
    """Wrong role: a patient made a therapist keeps their sessions (--force), but as a
    therapist sees only linked patients' data."""
    ids = users["pat"].id, history["squat_1"]
    assert get(client, clerk, "pat", route, *ids).status_code == 200
    users["pat"].role = Role.THERAPIST
    db.commit()

    response = get(client, clerk, "pat", route, *ids)

    assert response.status_code == 404


@pytest.mark.parametrize("route", ROUTES)
def test_a_therapist_cannot_see_a_former_patient(
    client, clerk, db, users, history, route
) -> None:
    """A linked user who is no longer a patient is not shown, as for plans. Making the
    patient a therapist (app/promote_therapist.py --force) keeps the link, but their
    therapist, still a therapist, gets the same 404 as for an unknown id."""
    ids = users["pat"].id, history["squat_1"]
    assert get(client, clerk, "ther", route, *ids).status_code == 200
    users["pat"].role = Role.THERAPIST
    db.commit()

    response = get(client, clerk, "ther", route, *ids)
    unknown = get(client, clerk, "ther", route, uuid.uuid4(), uuid.uuid4())

    assert response.status_code == 404
    assert response.json() == unknown.json()


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer not-a-jwt"}], ids=["no token", "bad"]
)
def test_no_valid_token_gets_401(client, users, history, route, headers) -> None:
    path = ROUTES[route].format(
        patient_id=users["pat"].id, session_id=history["squat_1"]
    )

    response = client.get(path, headers=headers)

    assert response.status_code == 401


@pytest.mark.parametrize("route", ROUTES)
def test_an_id_that_is_not_a_uuid_gets_422(client, clerk, users, route) -> None:
    response = get(client, clerk, "pat", route, "not-a-uuid", "not-a-uuid")

    assert response.status_code == 422


# What the frontend relies on


def test_polling_route_is_unchanged(client, clerk, users, history) -> None:
    """GET /sessions/{session_id}, which the upload page polls, still answers with the
    same four fields, without the result."""
    response = client.get(
        f"/sessions/{history['squat_1']}", headers=clerk.headers("user_pat")
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "plan_exercise_id", "status", "created_at"}
    assert (body["id"], body["status"]) == (str(history["squat_1"]), "complete")
    schema = app.openapi()["components"]["schemas"]["SessionResponse"]
    assert set(schema["properties"]) == set(body)


def test_openapi_names_the_hooks_and_types() -> None:
    """The frontend's hooks are useListPatientSessions(), useGetSessionResult(), and
    useGetPatientProgress() in src/api/results.ts, and a result has the contract's
    AnalysisResult type."""
    spec = app.openapi()

    operations = {
        operation["operationId"]: (method.upper(), path)
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if operation["tags"] == ["results"]
    }
    assert operations == {
        "list_patient_sessions": ("GET", "/patients/{patient_id}/sessions"),
        "get_session_result": ("GET", "/sessions/{session_id}/result"),
        "get_patient_progress": ("GET", "/patients/{patient_id}/progress"),
    }
    schemas = spec["components"]["schemas"]
    assert schemas["SessionResultResponse"]["properties"]["result"] == {
        "anyOf": [{"$ref": "#/components/schemas/AnalysisResult"}, {"type": "null"}]
    }
    assert set(schemas["AnalysisResult"]["properties"]) == set(
        AnalysisResult.model_fields
    )
