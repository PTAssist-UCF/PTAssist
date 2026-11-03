"""Tests for the local development seed (app/seed.py)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ExerciseKind, Plan, PlanExercise, Role, TherapistPatient, User
from app.seed import PATIENT_CLERK_ID, THERAPIST_CLERK_ID, SeedError, seed


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_seed_makes_a_linked_patient_with_a_plan(db: Session) -> None:
    plan = seed(db)

    therapist = db.get(User, plan.therapist_id)
    patient = db.get(User, plan.patient_id)
    assert (therapist.clerk_id, therapist.role) == (THERAPIST_CLERK_ID, Role.THERAPIST)
    assert (patient.clerk_id, patient.role) == (PATIENT_CLERK_ID, Role.PATIENT)
    assert count(db, TherapistPatient) == 1
    # Every exercise, with the right kind of target.
    assert len(plan.exercises) == 5
    for item in plan.exercises:
        is_hold = item.exercise.kind == ExerciseKind.HOLD
        assert (item.hold_seconds is not None) == is_hold
        assert (item.reps is not None) == (not is_hold)


def test_running_the_seed_again_adds_nothing(db: Session) -> None:
    first = seed(db)
    second = seed(db)

    assert second.id == first.id
    assert count(db, User) == 2
    assert count(db, TherapistPatient) == 1
    assert count(db, Plan) == 1
    assert count(db, PlanExercise) == 5


def test_seed_can_give_the_plan_to_an_existing_patient(db: Session) -> None:
    me = User(clerk_id="user_me", email="me@example.com", role=Role.PATIENT)
    db.add(me)
    db.commit()

    plan = seed(db, patient_email="me@example.com")

    assert plan.patient_id == me.id
    assert db.scalar(select(User).where(User.clerk_id == PATIENT_CLERK_ID)) is None


@pytest.mark.parametrize(
    ("role", "email", "message"),
    [
        (Role.PATIENT, "nobody@example.com", "Sign in to the web app once first"),
        (Role.THERAPIST, "ther@example.com", "not a patient"),
    ],
    ids=["unknown email", "not a patient"],
)
def test_seed_refuses_a_patient_email_it_cannot_use(
    db: Session, role: Role, email: str, message: str
) -> None:
    db.add(User(clerk_id="user_t", email="ther@example.com", role=role))
    db.commit()

    with pytest.raises(SeedError, match=message):
        seed(db, patient_email=email)


def test_the_seed_command_runs(db: Session) -> None:
    """python -m app.seed, as a developer runs it. conftest set DATABASE_URL to the
    test database, and the command inherits it."""
    backend = Path(__file__).parents[1]

    done = subprocess.run(
        [sys.executable, "-m", "app.seed"],
        cwd=backend,
        env=os.environ,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert done.returncode == 0, done.stderr
    assert "has 5 exercises" in done.stdout
    assert count(db, Plan) == 1
