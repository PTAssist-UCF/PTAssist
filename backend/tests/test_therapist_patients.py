"""Tests for /therapist/patients: linking patients by email, listing, unlinking."""

import logging
import uuid
from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.ownership import get_link
from app.main import app
from app.models import (
    Exercise,
    ExerciseSession,
    Plan,
    PlanExercise,
    Role,
    SessionStatus,
    TherapistPatient,
    User,
)


@pytest.fixture
def users(db: Session) -> dict[str, User]:
    """Two therapists and two patients, nobody linked yet. A user's Clerk id is
    user_<name> and their email <name>@example.com."""
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
    db.commit()
    return users


def link(client, clerk, email: str, user: str = "user_ther"):
    return client.post(
        "/therapist/patients", json={"email": email}, headers=clerk.headers(user)
    )


def links(db: Session) -> set[tuple[uuid.UUID, uuid.UUID]]:
    """Every saved link, as (therapist id, patient id)."""
    query = select(TherapistPatient.therapist_id, TherapistPatient.patient_id)
    return {tuple(row) for row in db.execute(query)}


def add_link(db: Session, therapist: User, patient: User) -> None:
    db.add(TherapistPatient(therapist_id=therapist.id, patient_id=patient.id))
    db.commit()


def test_therapist_links_a_patient_by_email(client, clerk, db, users) -> None:
    response = link(client, clerk, "pat@example.com")

    assert response.status_code == 201
    saved = get_link(db, users["ther"].id, users["pat"].id)
    assert saved is not None
    body = response.json()
    assert set(body) == {"id", "email", "linked_at"}
    assert body["id"] == str(users["pat"].id)
    assert body["email"] == "pat@example.com"
    assert datetime.fromisoformat(body["linked_at"]) == saved.created_at


def test_email_case_and_spaces_do_not_matter(client, clerk, db, users) -> None:
    mixed = User(
        clerk_id="user_mixed", email="Mixed.Case@Example.com", role=Role.PATIENT
    )
    db.add(mixed)
    db.commit()

    typed = link(client, clerk, "  PAT@Example.COM ")
    saved = link(client, clerk, "mixed.case@example.com")

    assert (typed.status_code, saved.status_code) == (201, 201)
    assert links(db) == {
        (users["ther"].id, users["pat"].id),
        (users["ther"].id, mixed.id),
    }


def test_email_without_a_patient_gets_the_same_404(client, clerk, db, users) -> None:
    """Nobody, another therapist, or the caller (so nobody can link themselves): the
    answer is the same, so it doesn't tell who has an account."""
    emails = ["nobody@example.com", "other_ther@example.com", "ther@example.com"]

    responses = [link(client, clerk, email) for email in emails]

    assert [response.status_code for response in responses] == [404, 404, 404]
    assert len({response.json()["detail"] for response in responses}) == 1
    assert links(db) == set()


def test_linking_twice_gets_409_and_keeps_one_link(client, clerk, db, users) -> None:
    first = link(client, clerk, "pat@example.com")
    second = link(client, clerk, "pat@example.com")

    assert first.status_code == 201
    assert second.status_code == 409
    assert links(db) == {(users["ther"].id, users["pat"].id)}


def test_email_shared_by_two_patients_gets_409(client, clerk, db, users) -> None:
    """Our copy of an email can be out of date. Never guess which patient is meant."""
    db.add(User(clerk_id="user_pat_2", email="pat@example.com", role=Role.PATIENT))
    db.commit()

    response = link(client, clerk, "pat@example.com")

    assert response.status_code == 409
    assert links(db) == set()


def test_a_patient_can_have_several_therapists(client, clerk, db, users) -> None:
    first = link(client, clerk, "pat@example.com", user="user_other_ther")
    second = link(client, clerk, "pat@example.com")

    assert (first.status_code, second.status_code) == (201, 201)
    assert links(db) == {
        (users["other_ther"].id, users["pat"].id),
        (users["ther"].id, users["pat"].id),
    }


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"email": ""},
        {"email": "   "},
        {"email": "a" * 321},
        {"email": "pat\u0000@example.com"},
    ],
    ids=["no email", "empty", "only spaces", "too long", "NUL character"],
)
def test_bad_email_gets_422(client, clerk, db, users, body) -> None:
    response = client.post(
        "/therapist/patients", json=body, headers=clerk.headers("user_ther")
    )

    assert response.status_code == 422
    assert links(db) == set()


def test_list_is_empty_before_linking(client, clerk, users) -> None:
    response = client.get("/therapist/patients", headers=clerk.headers("user_ther"))

    assert response.status_code == 200
    assert response.json() == []


def test_list_returns_the_linked_patients_by_email(client, clerk, users) -> None:
    pat = link(client, clerk, "pat@example.com").json()
    other_pat = link(client, clerk, "other_pat@example.com").json()

    response = client.get("/therapist/patients", headers=clerk.headers("user_ther"))

    assert response.status_code == 200
    assert response.json() == [other_pat, pat]  # the same as linking answered


def test_list_shows_only_the_callers_own_links(client, clerk, db, users) -> None:
    """Wrong owner: another therapist's links never show up."""
    add_link(db, users["ther"], users["pat"])
    add_link(db, users["other_ther"], users["other_pat"])

    mine = client.get("/therapist/patients", headers=clerk.headers("user_ther"))
    theirs = client.get("/therapist/patients", headers=clerk.headers("user_other_ther"))

    assert [patient["id"] for patient in mine.json()] == [str(users["pat"].id)]
    assert [patient["id"] for patient in theirs.json()] == [str(users["other_pat"].id)]


def test_unlinking_removes_only_the_link(client, clerk, db, users) -> None:
    """The plan and its sessions stay (results are kept), but the therapist no longer
    sees them, because therapists see only linked patients' data."""
    add_link(db, users["ther"], users["pat"])
    squat = db.scalars(select(Exercise).where(Exercise.name == "squat")).one()
    plan = Plan(therapist_id=users["ther"].id, patient_id=users["pat"].id)
    target = PlanExercise(plan=plan, exercise=squat, reps=10, sets=3, times_per_week=3)
    session = ExerciseSession(
        plan_exercise=target,
        status=SessionStatus.COMPLETE,
        video_key=f"sessions/{uuid.uuid4()}.mp4",
    )
    db.add(session)
    db.commit()
    therapist, patient = clerk.headers("user_ther"), clerk.headers("user_pat")
    session_url = f"/sessions/{session.id}"
    assert client.get(session_url, headers=therapist).status_code == 200

    response = client.delete(
        f"/therapist/patients/{users['pat'].id}", headers=therapist
    )

    assert response.status_code == 204
    assert response.content == b""
    assert links(db) == set()
    assert db.scalar(select(func.count()).select_from(Plan)) == 1
    assert db.scalar(select(func.count()).select_from(ExerciseSession)) == 1
    assert client.get(session_url, headers=therapist).status_code == 404
    assert client.get(session_url, headers=patient).status_code == 200


def test_unlinking_another_therapists_link_gets_404(client, clerk, db, users) -> None:
    """Wrong owner: 404, not 403, so it doesn't tell who is linked. Their link stays."""
    add_link(db, users["other_ther"], users["pat"])

    response = client.delete(
        f"/therapist/patients/{users['pat'].id}", headers=clerk.headers("user_ther")
    )

    assert response.status_code == 404
    assert links(db) == {(users["other_ther"].id, users["pat"].id)}


@pytest.mark.parametrize("who", ["unknown id", "unlinked patient", "the caller"])
def test_unlinking_someone_not_linked_gets_404(client, clerk, db, users, who) -> None:
    patient_id = {
        "unknown id": uuid.uuid4(),
        "unlinked patient": users["other_pat"].id,
        "the caller": users["ther"].id,
    }[who]
    add_link(db, users["ther"], users["pat"])

    response = client.delete(
        f"/therapist/patients/{patient_id}", headers=clerk.headers("user_ther")
    )

    assert response.status_code == 404
    assert links(db) == {(users["ther"].id, users["pat"].id)}


ENDPOINTS = {
    "link": ("POST", "/therapist/patients"),
    "list": ("GET", "/therapist/patients"),
    "unlink": ("DELETE", "/therapist/patients/{patient_id}"),
}


def call(client, endpoint: str, patient: User, headers: dict[str, str]):
    """Call one endpoint about this patient: link their email, list, or unlink them."""
    method, path = ENDPOINTS[endpoint]
    body = {"email": patient.email} if method == "POST" else None
    url = path.format(patient_id=patient.id)
    return client.request(method, url, json=body, headers=headers)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_patient_gets_403(client, clerk, db, users, endpoint) -> None:
    """Wrong role: a patient can't link, list, or unlink patients."""
    add_link(db, users["ther"], users["other_pat"])

    response = call(client, endpoint, users["other_pat"], clerk.headers("user_pat"))

    assert response.status_code == 403
    assert links(db) == {(users["ther"].id, users["other_pat"].id)}


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer not-a-jwt"}], ids=["no token", "bad"]
)
def test_no_valid_token_gets_401(client, db, users, endpoint, headers) -> None:
    add_link(db, users["ther"], users["pat"])

    response = call(client, endpoint, users["pat"], headers)

    assert response.status_code == 401
    assert links(db) == {(users["ther"].id, users["pat"].id)}


def test_emails_are_not_logged(client, clerk, users, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    # As if someone turned on SQL logging to debug (SQLAlchemy keeps it off by default).
    caplog.set_level(logging.INFO, logger="sqlalchemy.engine")

    assert link(client, clerk, "pat@example.com").status_code == 201
    assert link(client, clerk, "nobody@example.com").status_code == 404

    assert "INSERT INTO therapist_patients" in caplog.text  # SQL is logged...
    assert "pat@example.com" not in caplog.text  # ...but not its values
    assert "nobody@example.com" not in caplog.text


def test_openapi_names_the_frontend_hooks() -> None:
    """The frontend's generated hooks are named after these: useLinkPatient(), etc."""
    paths = app.openapi()["paths"]

    operations = {
        operation["operationId"]: (method.upper(), path, operation["tags"])
        for path, item in paths.items()
        if path.startswith("/therapist/patients")
        for method, operation in item.items()
    }

    assert operations == {
        "link_patient": ("POST", "/therapist/patients", ["patients"]),
        "list_linked_patients": ("GET", "/therapist/patients", ["patients"]),
        "unlink_patient": ("DELETE", "/therapist/patients/{patient_id}", ["patients"]),
    }
