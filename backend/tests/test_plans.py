"""Tests for plans: GET and PUT /therapist/patients/{patient_id}/plan (therapists save
and read a linked patient's plan) and GET /plans/me (a patient reads their own)."""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import engine
from app.main import app
from app.models import (
    Exercise,
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
from app.schemas.plan import MAX_HOLD_SECONDS, MAX_REPS, MAX_SETS


@pytest.fixture
def users(db: Session) -> dict[str, User]:
    """Two therapists and two patients: ther is linked to pat, and other_ther to
    other_pat. A user's Clerk id is user_<name> and their email <name>@example.com."""
    users = {
        name: User(clerk_id=f"user_{name}", email=f"{name}@example.com", role=role)
        for name, role in [
            ("ther", Role.THERAPIST),
            ("other_ther", Role.THERAPIST),
            ("pat", Role.PATIENT),
            ("other_pat", Role.PATIENT),
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
def ids(db: Session) -> dict[str, uuid.UUID]:
    """Each library exercise's id, by name, such as ids["squat"]."""
    return {exercise.name: exercise.id for exercise in db.scalars(select(Exercise))}


def item(ids: dict[str, uuid.UUID], name: str, **targets: Any) -> dict[str, Any]:
    """One exercise of a save's body: 3 sets, 3 times a week, and the targets given."""
    return {"exercise_id": str(ids[name]), "sets": 3, "times_per_week": 3, **targets}


def plan_url(patient_id: uuid.UUID) -> str:
    return f"/therapist/patients/{patient_id}/plan"


def save(client, clerk, patient_id: uuid.UUID, exercises, user: str = "user_ther"):
    return client.put(
        plan_url(patient_id), json={"exercises": exercises}, headers=clerk.headers(user)
    )


def read(client, clerk, patient_id: uuid.UUID, user: str = "user_ther"):
    return client.get(plan_url(patient_id), headers=clerk.headers(user))


def my_plan(client, clerk, user: str = "user_pat"):
    return client.get("/plans/me", headers=clerk.headers(user))


def by_name(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """A plan answer's exercises, by exercise name."""
    return {item["exercise"]["name"]: item for item in plan["exercises"]}


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model))


def add_upload(db: Session, plan_exercise_id: str) -> uuid.UUID:
    """An analyzed upload (a session and its result) for this plan exercise."""
    session = ExerciseSession(
        plan_exercise_id=uuid.UUID(plan_exercise_id),
        status=SessionStatus.FAILED,
        video_key=f"sessions/{uuid.uuid4()}.mp4",
    )
    db.add(session)
    db.flush()
    failed = AnalysisResult.failed("analysis_timed_out", analyzer_version=None)
    db.add(SessionResult(session_id=session.id, result=failed.model_dump(mode="json")))
    db.commit()
    return session.id


# Saving


def test_therapist_creates_a_plan_for_a_linked_patient(
    client, clerk, db, users, ids
) -> None:
    response = save(
        client,
        clerk,
        users["pat"].id,
        [
            item(ids, "squat", reps=10),
            item(ids, "plank", hold_seconds=30, sets=2, times_per_week=5),
        ],
    )

    assert response.status_code == 201
    plan = db.scalars(select(Plan)).one()
    assert (plan.therapist_id, plan.patient_id) == (users["ther"].id, users["pat"].id)
    rows = {row.exercise_id: row for row in db.scalars(select(PlanExercise))}
    body = response.json()
    assert body["id"] == str(plan.id)
    assert body["patient_id"] == str(users["pat"].id)
    assert datetime.fromisoformat(body["created_at"]) == plan.created_at
    # In the library's order (by display name), so Plank before Squat.
    assert body["exercises"] == [
        {
            "id": str(rows[ids["plank"]].id),
            "exercise": {
                "id": str(ids["plank"]),
                "name": "plank",
                "display_name": "Plank",
                "kind": "hold",
            },
            "reps": None,
            "hold_seconds": 30,
            "sets": 2,
            "times_per_week": 5,
        },
        {
            "id": str(rows[ids["squat"]].id),
            "exercise": {
                "id": str(ids["squat"]),
                "name": "squat",
                "display_name": "Squat",
                "kind": "reps",
            },
            "reps": 10,
            "hold_seconds": None,
            "sets": 3,
            "times_per_week": 3,
        },
    ]


def test_saving_again_updates_the_plan_in_place(client, clerk, db, users, ids) -> None:
    """An exercise that stays keeps its id (the patient's upload link) and gets the new
    targets. A new one is added, and one left out (with no uploads) is removed."""
    first = save(
        client,
        clerk,
        users["pat"].id,
        [item(ids, "squat", reps=10), item(ids, "plank", hold_seconds=30)],
    ).json()

    response = save(
        client,
        clerk,
        users["pat"].id,
        [
            item(ids, "squat", reps=12, sets=4, times_per_week=2),
            item(ids, "cat_cow", reps=8),
        ],
    )

    assert response.status_code == 200
    second = response.json()
    assert (second["id"], second["created_at"]) == (first["id"], first["created_at"])
    assert count(db, Plan) == 1
    squat = by_name(second)["squat"]
    assert squat["id"] == by_name(first)["squat"]["id"]
    assert (squat["reps"], squat["sets"], squat["times_per_week"]) == (12, 4, 2)
    assert set(by_name(second)) == {"squat", "cat_cow"}
    assert set(db.scalars(select(PlanExercise.exercise_id))) == {
        ids["squat"],
        ids["cat_cow"],
    }


def test_an_exercise_with_uploads_keeps_them_when_its_targets_change(
    client, clerk, db, users, ids
) -> None:
    plan = save(client, clerk, users["pat"].id, [item(ids, "squat", reps=10)]).json()
    squat_id = by_name(plan)["squat"]["id"]
    session_id = add_upload(db, squat_id)

    response = save(
        client,
        clerk,
        users["pat"].id,
        [item(ids, "squat", reps=15), item(ids, "plank", hold_seconds=45)],
    )

    assert response.status_code == 200
    assert by_name(response.json())["squat"]["id"] == squat_id
    db.expire_all()  # read the session and its result from the database again
    assert str(db.get(ExerciseSession, session_id).plan_exercise_id) == squat_id
    assert db.get(SessionResult, session_id) is not None


def test_an_exercise_with_uploads_cannot_be_removed(
    client, clerk, db, users, ids
) -> None:
    """Results are kept, so the save is refused with 409, and nothing changes: not even
    the targets of the exercises it kept."""
    plan = save(
        client,
        clerk,
        users["pat"].id,
        [item(ids, "squat", reps=10), item(ids, "plank", hold_seconds=30)],
    ).json()
    add_upload(db, by_name(plan)["squat"]["id"])

    response = save(
        client, clerk, users["pat"].id, [item(ids, "plank", hold_seconds=60)]
    )

    assert response.status_code == 409
    assert "Squat" in response.json()["detail"]
    assert read(client, clerk, users["pat"].id).json() == plan
    assert count(db, ExerciseSession) == 1
    assert count(db, SessionResult) == 1


def test_a_patient_has_one_plan_whichever_linked_therapist_saves_it(
    client, clerk, db, users, ids
) -> None:
    """A second therapist linked to the patient changes the same plan, instead of
    making another one. The plan still records who made it."""
    db.add(
        TherapistPatient(
            therapist_id=users["other_ther"].id, patient_id=users["pat"].id
        )
    )
    db.commit()

    first = save(client, clerk, users["pat"].id, [item(ids, "squat", reps=10)])
    second = save(
        client,
        clerk,
        users["pat"].id,
        [item(ids, "squat", reps=20)],
        user="user_other_ther",
    )

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["id"] == first.json()["id"]
    plan = db.scalars(select(Plan)).one()
    assert plan.therapist_id == users["ther"].id
    assert read(client, clerk, users["pat"].id).json() == second.json()


def test_targets_at_the_limits_are_accepted(client, clerk, users, ids) -> None:
    response = save(
        client,
        clerk,
        users["pat"].id,
        [
            item(ids, "squat", reps=MAX_REPS, sets=MAX_SETS, times_per_week=7),
            item(ids, "plank", hold_seconds=MAX_HOLD_SECONDS, sets=1, times_per_week=1),
            item(ids, "cat_cow", reps=1),
        ],
    )

    assert response.status_code == 201


BAD_BODIES = {
    "no exercises": lambda ids: {},
    "an empty list": lambda ids: {"exercises": []},
    "no exercise_id": lambda ids: {
        "exercises": [{"reps": 10, "sets": 3, "times_per_week": 3}]
    },
    "exercise_id not a UUID": lambda ids: {
        "exercises": [{**item(ids, "squat", reps=10), "exercise_id": "squat"}]
    },
    "both reps and hold_seconds": lambda ids: {
        "exercises": [item(ids, "plank", reps=10, hold_seconds=30)]
    },
    "neither reps nor hold_seconds": lambda ids: {"exercises": [item(ids, "squat")]},
    "zero reps": lambda ids: {"exercises": [item(ids, "squat", reps=0)]},
    "too many reps": lambda ids: {"exercises": [item(ids, "squat", reps=MAX_REPS + 1)]},
    "reps not a whole number": lambda ids: {
        "exercises": [item(ids, "squat", reps=10.5)]
    },
    "zero hold": lambda ids: {"exercises": [item(ids, "plank", hold_seconds=0)]},
    "a hold longer than a clip": lambda ids: {
        "exercises": [item(ids, "plank", hold_seconds=MAX_HOLD_SECONDS + 1)]
    },
    "no sets": lambda ids: {
        "exercises": [
            {"exercise_id": str(ids["squat"]), "reps": 10, "times_per_week": 3}
        ]
    },
    "zero sets": lambda ids: {"exercises": [item(ids, "squat", reps=10, sets=0)]},
    "too many sets": lambda ids: {
        "exercises": [item(ids, "squat", reps=10, sets=MAX_SETS + 1)]
    },
    "zero times a week": lambda ids: {
        "exercises": [item(ids, "squat", reps=10, times_per_week=0)]
    },
    "eight times a week": lambda ids: {
        "exercises": [item(ids, "squat", reps=10, times_per_week=8)]
    },
    "the same exercise twice": lambda ids: {
        "exercises": [item(ids, "squat", reps=10), item(ids, "squat", reps=12)]
    },
    "an unknown exercise": lambda ids: {
        "exercises": [{**item(ids, "squat", reps=10), "exercise_id": str(uuid.uuid4())}]
    },
    "reps for a hold exercise": lambda ids: {
        "exercises": [item(ids, "plank", reps=10)]
    },
    "hold_seconds for a reps exercise": lambda ids: {
        "exercises": [item(ids, "squat", hold_seconds=30)]
    },
}


@pytest.mark.parametrize("make_body", BAD_BODIES.values(), ids=list(BAD_BODIES))
def test_bad_plan_gets_422(client, clerk, db, users, ids, make_body) -> None:
    response = client.put(
        plan_url(users["pat"].id),
        json=make_body(ids),
        headers=clerk.headers("user_ther"),
    )

    assert response.status_code == 422
    assert count(db, Plan) == 0


def test_a_target_must_fit_the_exercise_kind(client, clerk, users, ids) -> None:
    """The database can't check this (the kind is in another table), so the save does,
    and says what to send instead. A refused save leaves the plan as it was."""
    plan = save(client, clerk, users["pat"].id, [item(ids, "squat", reps=10)]).json()

    hold = save(client, clerk, users["pat"].id, [item(ids, "plank", reps=10)])
    reps = save(client, clerk, users["pat"].id, [item(ids, "squat", hold_seconds=30)])

    assert (hold.status_code, reps.status_code) == (422, 422)
    assert hold.json()["detail"] == (
        "Plank is held for time, so its target is hold_seconds, not reps"
    )
    assert reps.json()["detail"] == (
        "Squat is done in reps, so its target is reps, not hold_seconds"
    )
    assert read(client, clerk, users["pat"].id).json() == plan


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_a_patient_id_that_is_not_a_uuid_gets_422(
    client, clerk, users, ids, method
) -> None:
    response = client.request(
        method,
        "/therapist/patients/not-a-uuid/plan",
        json={"exercises": [item(ids, "squat", reps=10)]} if method == "PUT" else None,
        headers=clerk.headers("user_ther"),
    )

    assert response.status_code == 422


# Reading


def test_therapist_reads_a_linked_patients_plan(client, clerk, users, ids) -> None:
    saved = save(client, clerk, users["pat"].id, [item(ids, "squat", reps=10)]).json()

    response = read(client, clerk, users["pat"].id)

    assert response.status_code == 200
    assert response.json() == saved


def test_a_linked_patient_without_a_plan_gets_404(client, clerk, users) -> None:
    response = read(client, clerk, users["pat"].id)

    assert response.status_code == 404
    assert response.json()["detail"] == "This patient has no plan yet"


def test_patient_reads_their_own_plan(client, clerk, db, users, ids) -> None:
    saved = save(
        client,
        clerk,
        users["pat"].id,
        [item(ids, "squat", reps=10), item(ids, "plank", hold_seconds=30)],
    ).json()

    response = my_plan(client, clerk)

    assert response.status_code == 200
    assert response.json() == saved
    # Each exercise's id is the plan_exercise_id to upload a video with: POST /sessions
    # takes a plan exercise whose plan is the patient's.
    for exercise in response.json()["exercises"]:
        row = db.get(PlanExercise, uuid.UUID(exercise["id"]))
        assert row.plan.patient_id == users["pat"].id


def test_a_patient_without_a_plan_gets_404(client, clerk, users, ids) -> None:
    """Even while another patient has one."""
    save(
        client,
        clerk,
        users["other_pat"].id,
        [item(ids, "squat", reps=10)],
        user="user_other_ther",
    )

    response = my_plan(client, clerk)

    assert response.status_code == 404
    assert "don't have a plan yet" in response.json()["detail"]


# Done when: a therapist cannot plan for an unlinked patient, and a patient sees only
# their own plan.


@pytest.mark.parametrize(
    "who", ["another therapist's patient", "an unknown id", "a therapist", "the caller"]
)
def test_a_therapist_cannot_plan_for_an_unlinked_patient(
    client, clerk, db, users, ids, who
) -> None:
    """404, the same answer whoever it is, so it doesn't tell who exists or who is
    linked to whom. No plan is made."""
    patient_id = {
        "another therapist's patient": users["other_pat"].id,
        "an unknown id": uuid.uuid4(),
        "a therapist": users["other_ther"].id,
        "the caller": users["ther"].id,
    }[who]

    response = save(client, clerk, patient_id, [item(ids, "squat", reps=10)])

    assert response.status_code == 404
    assert response.json()["detail"] == "Patient not found"
    assert count(db, Plan) == 0


def test_a_therapist_cannot_see_or_change_an_unlinked_patients_plan(
    client, clerk, users, ids
) -> None:
    """Wrong owner: other_pat's plan belongs to other_ther's patient. The answers are
    the same as for a patient without a plan, or an unknown id."""
    theirs = save(
        client,
        clerk,
        users["other_pat"].id,
        [item(ids, "squat", reps=10)],
        user="user_other_ther",
    ).json()

    seen = read(client, clerk, users["other_pat"].id)
    changed = save(client, clerk, users["other_pat"].id, [item(ids, "squat", reps=50)])

    assert (seen.status_code, changed.status_code) == (404, 404)
    assert seen.json()["detail"] == changed.json()["detail"] == "Patient not found"
    assert (
        read(client, clerk, users["other_pat"].id, "user_other_ther").json() == theirs
    )


def test_a_patient_sees_only_their_own_plan(client, clerk, users, ids) -> None:
    mine = save(client, clerk, users["pat"].id, [item(ids, "squat", reps=10)]).json()
    theirs = save(
        client,
        clerk,
        users["other_pat"].id,
        [item(ids, "plank", hold_seconds=30)],
        user="user_other_ther",
    ).json()

    assert my_plan(client, clerk, "user_pat").json() == mine
    assert my_plan(client, clerk, "user_other_pat").json() == theirs
    assert mine["id"] != theirs["id"]


def test_after_unlinking_the_plan_stays_with_the_patient(
    client, clerk, users, ids
) -> None:
    """The patient still sees it. The unlinked therapist no longer sees or changes it,
    and a therapist who links the patient later does."""
    saved = save(client, clerk, users["pat"].id, [item(ids, "squat", reps=10)]).json()
    therapist = clerk.headers("user_ther")
    unlinked = client.delete(
        f"/therapist/patients/{users['pat'].id}", headers=therapist
    )
    assert unlinked.status_code == 204

    assert read(client, clerk, users["pat"].id).status_code == 404
    assert (
        save(client, clerk, users["pat"].id, [item(ids, "squat", reps=5)]).status_code
        == 404
    )
    assert my_plan(client, clerk).json() == saved
    linked = client.post(
        "/therapist/patients",
        json={"email": "pat@example.com"},
        headers=clerk.headers("user_other_ther"),
    )
    assert linked.status_code == 201
    assert read(client, clerk, users["pat"].id, "user_other_ther").json() == saved


def test_a_linked_user_who_is_no_longer_a_patient_gets_404(
    client, clerk, db, users, ids
) -> None:
    """Only patients have plans. Making a linked patient a therapist (the promote script
    with --force) keeps the link, but they are not found as a patient."""
    users["pat"].role = Role.THERAPIST
    db.commit()

    saved = save(client, clerk, users["pat"].id, [item(ids, "squat", reps=10)])
    seen = read(client, clerk, users["pat"].id)

    assert (saved.status_code, seen.status_code) == (404, 404)
    assert count(db, Plan) == 0


# Wrong role, no token


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_a_patient_gets_403_on_the_therapist_endpoints(
    client, clerk, users, ids, method
) -> None:
    """Wrong role: a patient can't read or save a plan this way, not even their own."""
    saved = save(client, clerk, users["pat"].id, [item(ids, "squat", reps=10)]).json()

    response = client.request(
        method,
        plan_url(users["pat"].id),
        json={"exercises": [item(ids, "squat", reps=99)]} if method == "PUT" else None,
        headers=clerk.headers("user_pat"),
    )

    assert response.status_code == 403
    assert my_plan(client, clerk).json() == saved


def test_a_therapist_gets_403_on_my_plan(client, clerk, users) -> None:
    """Wrong role: /plans/me is the caller's own plan, and only patients have one."""
    response = my_plan(client, clerk, "user_ther")

    assert response.status_code == 403


ENDPOINTS = {
    "read": ("GET", "/therapist/patients/{patient_id}/plan"),
    "save": ("PUT", "/therapist/patients/{patient_id}/plan"),
    "my plan": ("GET", "/plans/me"),
}


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer not-a-jwt"}], ids=["no token", "bad"]
)
def test_no_valid_token_gets_401(client, db, users, ids, endpoint, headers) -> None:
    method, path = ENDPOINTS[endpoint]

    response = client.request(
        method,
        path.format(patient_id=users["pat"].id),
        json={"exercises": [item(ids, "squat", reps=10)]} if method == "PUT" else None,
        headers=headers,
    )

    assert response.status_code == 401
    assert count(db, Plan) == 0


# Saves at the same time as another save, or as an upload


def wait_for_a_lock() -> None:
    """Wait (up to 10 seconds) until a query in the test database is waiting for a lock
    that another transaction holds."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        # A new transaction each time: Postgres shows a transaction the same
        # pg_stat_activity until it ends.
        with engine.connect() as connection:
            waiting = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            )
        if waiting:
            return
        time.sleep(0.05)
    pytest.fail("No query waited for the lock")


def test_two_saves_at_once_make_one_plan(client, clerk, db, users, ids) -> None:
    """The database allows a patient several plans, so a save first locks the patient's
    row. Here another save holds that lock and makes the plan: the waiting save then
    updates that plan, instead of making a second one."""
    therapist_id, patient_id = users["ther"].id, users["pat"].id
    # The pool waits for the save when it closes, so it is opened first: the other
    # save's session closes before it, giving up the lock even if the test fails.
    with ThreadPoolExecutor(max_workers=1) as pool, Session(engine) as other:
        other.execute(select(User.id).where(User.id == patient_id).with_for_update())
        waiting = pool.submit(
            save, client, clerk, patient_id, [item(ids, "squat", reps=10)]
        )
        wait_for_a_lock()
        other.add(Plan(therapist_id=therapist_id, patient_id=patient_id))
        other.commit()
        response = waiting.result(timeout=10)

    assert response.status_code == 200  # it updated the plan the other save made
    assert count(db, Plan) == 1
    assert count(db, PlanExercise) == 1


def test_a_save_waits_for_an_upload_being_saved(client, clerk, db, users, ids) -> None:
    """An upload saving a session locks its plan exercise until it commits (the
    session's foreign key). A save that leaves that exercise out waits for it, sees the
    new session, and answers 409, instead of missing it (and failing with a 500)."""
    plan = save(
        client,
        clerk,
        users["pat"].id,
        [item(ids, "squat", reps=10), item(ids, "plank", hold_seconds=30)],
    ).json()
    squat_id, patient_id = by_name(plan)["squat"]["id"], users["pat"].id
    with ThreadPoolExecutor(max_workers=1) as pool, Session(engine) as upload:
        upload.add(
            ExerciseSession(
                plan_exercise_id=uuid.UUID(squat_id),
                status=SessionStatus.PROCESSING,
                video_key=f"sessions/{uuid.uuid4()}.mp4",
            )
        )
        upload.flush()  # saved, but not committed yet
        waiting = pool.submit(
            save, client, clerk, patient_id, [item(ids, "plank", hold_seconds=30)]
        )
        wait_for_a_lock()
        upload.commit()
        response = waiting.result(timeout=10)

    assert response.status_code == 409
    assert count(db, ExerciseSession) == 1
    assert count(db, PlanExercise) == 2


def test_openapi_names_the_frontend_hooks() -> None:
    """The frontend's generated hooks are named after these: useGetMyPlan(), etc."""
    paths = app.openapi()["paths"]

    operations = {
        operation["operationId"]: (method.upper(), path, operation["tags"])
        for path, path_item in paths.items()
        if path.endswith("/plan") or path.startswith("/plans")
        for method, operation in path_item.items()
    }

    assert operations == {
        "get_patient_plan": ("GET", "/therapist/patients/{patient_id}/plan", ["plans"]),
        "save_patient_plan": (
            "PUT",
            "/therapist/patients/{patient_id}/plan",
            ["plans"],
        ),
        "get_my_plan": ("GET", "/plans/me", ["plans"]),
    }
    # The save answers 201 when it creates the plan, and 200 when it updates it.
    save_responses = paths["/therapist/patients/{patient_id}/plan"]["put"]["responses"]
    assert {"200", "201"} <= set(save_responses)
