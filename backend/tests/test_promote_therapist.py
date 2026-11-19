"""Tests for the script that promotes therapists (app/promote_therapist.py)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Plan, Role, TherapistPatient, User
from app.promote_therapist import RoleChangeError, set_role


def add_user(db: Session, name: str, role: Role) -> User:
    user = User(clerk_id=f"user_{name}", email=f"{name}@example.com", role=role)
    db.add(user)
    db.commit()
    return user


def link(db: Session, therapist: User, patient: User) -> None:
    db.add(TherapistPatient(therapist_id=therapist.id, patient_id=patient.id))
    db.commit()


def saved_role(db: Session, user: User) -> str:
    """The user's role as stored in the database."""
    return db.scalar(select(User.role).where(User.id == user.id))


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_promotes_a_patient(db: Session) -> None:
    # Other people's links and plans don't matter.
    therapist = add_user(db, "ther", Role.THERAPIST)
    patient = add_user(db, "pat", Role.PATIENT)
    link(db, therapist, patient)
    db.add(Plan(therapist_id=therapist.id, patient_id=patient.id))
    db.commit()
    new = add_user(db, "new", Role.PATIENT)

    user, changed = set_role(db, "new@example.com", Role.THERAPIST)

    assert (user.id, changed) == (new.id, True)
    assert saved_role(db, new) == Role.THERAPIST
    assert saved_role(db, patient) == Role.PATIENT


def test_the_email_can_differ_in_case_and_spaces(db: Session) -> None:
    jane = add_user(db, "jane", Role.PATIENT)

    set_role(db, "  Jane@Example.COM ", Role.THERAPIST)

    assert saved_role(db, jane) == Role.THERAPIST


def test_a_therapist_is_left_as_is(db: Session) -> None:
    therapist = add_user(db, "ther", Role.THERAPIST)
    link(db, therapist, add_user(db, "pat", Role.PATIENT))

    user, changed = set_role(db, "ther@example.com", Role.THERAPIST)

    assert (user.id, changed) == (therapist.id, False)
    assert saved_role(db, therapist) == Role.THERAPIST


def test_an_unknown_email_is_refused(db: Session) -> None:
    add_user(db, "pat", Role.PATIENT)

    with pytest.raises(RoleChangeError, match="sign in to the web app once first"):
        set_role(db, "nobody@example.com", Role.THERAPIST)


def test_an_email_of_two_users_is_refused(db: Session) -> None:
    """Possible if someone deletes their Clerk account and signs up again."""
    db.add(User(clerk_id="user_old", email="twin@example.com", role=Role.PATIENT))
    db.add(User(clerk_id="user_new", email="Twin@example.com", role=Role.PATIENT))
    db.commit()

    with pytest.raises(RoleChangeError, match="2 users have that email"):
        set_role(db, "twin@example.com", Role.THERAPIST)

    roles = db.scalars(select(User.role)).all()
    assert roles == [Role.PATIENT, Role.PATIENT]


@pytest.mark.parametrize("has", ["therapist", "plan"])
def test_a_patient_with_a_therapist_or_a_plan_is_refused(db: Session, has: str) -> None:
    """Most likely the wrong email: a new therapist has only signed in once."""
    therapist = add_user(db, "ther", Role.THERAPIST)
    patient = add_user(db, "pat", Role.PATIENT)
    if has == "therapist":
        link(db, therapist, patient)
    else:
        db.add(Plan(therapist_id=therapist.id, patient_id=patient.id))
        db.commit()

    with pytest.raises(RoleChangeError, match="run it again with --force"):
        set_role(db, "pat@example.com", Role.THERAPIST)

    assert saved_role(db, patient) == Role.PATIENT


def test_force_promotes_a_patient_with_a_therapist_and_keeps_their_data(
    db: Session,
) -> None:
    therapist = add_user(db, "ther", Role.THERAPIST)
    patient = add_user(db, "pat", Role.PATIENT)
    link(db, therapist, patient)
    db.add(Plan(therapist_id=therapist.id, patient_id=patient.id))
    db.commit()

    _, changed = set_role(db, "pat@example.com", Role.THERAPIST, force=True)

    assert changed
    assert saved_role(db, patient) == Role.THERAPIST
    assert (count(db, TherapistPatient), count(db, Plan)) == (1, 1)


def test_demote_makes_a_therapist_a_patient(db: Session) -> None:
    therapist = add_user(db, "ther", Role.THERAPIST)

    _, changed = set_role(db, "ther@example.com", Role.PATIENT)

    assert changed
    assert saved_role(db, therapist) == Role.PATIENT


def test_demote_refuses_a_therapist_with_patients_unless_forced(db: Session) -> None:
    therapist = add_user(db, "ther", Role.THERAPIST)
    link(db, therapist, add_user(db, "pat", Role.PATIENT))

    with pytest.raises(RoleChangeError, match="run it again with --force"):
        set_role(db, "ther@example.com", Role.PATIENT)
    assert saved_role(db, therapist) == Role.THERAPIST

    set_role(db, "ther@example.com", Role.PATIENT, force=True)
    assert saved_role(db, therapist) == Role.PATIENT


def run_command(*args: str) -> subprocess.CompletedProcess[str]:
    """python -m app.promote_therapist, as the team runs it. conftest set DATABASE_URL
    to the test database, and the command inherits it."""
    return subprocess.run(
        [sys.executable, "-m", "app.promote_therapist", *args],
        cwd=Path(__file__).parents[1],
        env=os.environ,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_the_command_promotes_and_prints_the_id_not_the_email(db: Session) -> None:
    new = add_user(db, "new", Role.PATIENT)

    first = run_command("--email", "new@example.com")
    again = run_command("--email", "new@example.com")

    assert first.returncode == 0, first.stderr
    assert f"User {new.id} is now a therapist." in first.stdout
    assert again.returncode == 0, again.stderr
    assert f"User {new.id} is already a therapist. Nothing changed." in again.stdout
    for done in (first, again):
        assert "new@example.com" not in done.stdout + done.stderr
    assert saved_role(db, new) == Role.THERAPIST


@pytest.mark.parametrize(
    ("email", "message"),
    [
        ("nobody@example.com", "sign in to the web app once first"),
        ("pat@example.com", "run it again with --force"),
    ],
    ids=["unknown email", "patient with a therapist"],
)
def test_the_command_fails_when_it_changes_nothing(
    db: Session, email: str, message: str
) -> None:
    therapist = add_user(db, "ther", Role.THERAPIST)
    patient = add_user(db, "pat", Role.PATIENT)
    link(db, therapist, patient)

    done = run_command("--email", email)

    assert done.returncode == 1
    assert done.stderr.startswith("Role not changed: ")
    assert message in done.stderr
    assert email not in done.stdout + done.stderr
    assert count(db, User) == 2
    assert saved_role(db, patient) == Role.PATIENT


def test_the_command_can_demote_with_force(db: Session) -> None:
    therapist = add_user(db, "ther", Role.THERAPIST)
    link(db, therapist, add_user(db, "pat", Role.PATIENT))

    done = run_command("--email", "ther@example.com", "--demote", "--force")

    assert done.returncode == 0, done.stderr
    assert f"User {therapist.id} is now a patient." in done.stdout
    assert saved_role(db, therapist) == Role.PATIENT
