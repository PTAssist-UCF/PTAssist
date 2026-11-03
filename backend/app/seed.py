"""Local development data: a therapist, a patient, a link between them, and a plan.

The exercise library is not made here: the migrations add it, so every database has it.

Run from backend/, against your local database only (DATABASE_URL), never Azure:

    python -m app.seed                                   # a placeholder patient
    python -m app.seed --patient-email you@example.com   # your own account instead

The placeholder users have no Clerk account, so nobody can sign in as them. To see the
plan in the web app, sign in once (which creates your user as a patient), then run the
seed with your email. Running it again adds nothing new.
"""

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import (
    Exercise,
    ExerciseKind,
    Plan,
    PlanExercise,
    Role,
    TherapistPatient,
    User,
)

# Placeholder users. Real Clerk ids start with "user_", so these never clash with one.
THERAPIST_CLERK_ID = "seed_therapist"
THERAPIST_EMAIL = "therapist@example.com"
PATIENT_CLERK_ID = "seed_patient"
PATIENT_EMAIL = "patient@example.com"

# Targets for the dev plan, by exercise name: reps per set (or hold seconds), sets,
# times per week. Made-up numbers for testing, not clinical advice.
DEV_TARGETS = {
    "squat": {"reps": 10, "sets": 3, "times_per_week": 3},
    "plank": {"hold_seconds": 30, "sets": 3, "times_per_week": 3},
    # rep_count counts both sides, so 20 is 10 per leg.
    "side_leg_raise": {"reps": 20, "sets": 2, "times_per_week": 3},
    "shoulder_abduction": {"reps": 10, "sets": 2, "times_per_week": 5},
    "cat_cow": {"reps": 8, "sets": 2, "times_per_week": 5},
}


class SeedError(Exception):
    """The seed can't run as asked. The message says why."""


def seed(db: Session, patient_email: str | None = None) -> Plan:
    """Add the dev data if it is missing, and return the patient's dev plan."""
    therapist = _get_or_create_user(
        db, THERAPIST_CLERK_ID, THERAPIST_EMAIL, Role.THERAPIST
    )
    if patient_email is None:
        patient = _get_or_create_user(db, PATIENT_CLERK_ID, PATIENT_EMAIL, Role.PATIENT)
    else:
        patient = _find_patient(db, patient_email)

    link = db.scalar(
        select(TherapistPatient).where(
            TherapistPatient.therapist_id == therapist.id,
            TherapistPatient.patient_id == patient.id,
        )
    )
    if link is None:
        db.add(TherapistPatient(therapist_id=therapist.id, patient_id=patient.id))

    plan = db.scalar(
        select(Plan).where(
            Plan.therapist_id == therapist.id, Plan.patient_id == patient.id
        )
    )
    if plan is None:
        plan = Plan(therapist_id=therapist.id, patient_id=patient.id)
        for exercise in db.scalars(select(Exercise).order_by(Exercise.name)):
            targets = DEV_TARGETS[exercise.name]
            # Catch a mismatch here, before the plan endpoints exist to check it.
            if ("hold_seconds" in targets) != (exercise.kind == ExerciseKind.HOLD):
                raise SeedError(f"DEV_TARGETS for {exercise.name} don't match its kind")
            plan.exercises.append(PlanExercise(exercise=exercise, **targets))
        db.add(plan)

    db.commit()
    return plan


def _get_or_create_user(db: Session, clerk_id: str, email: str, role: Role) -> User:
    user = db.scalar(select(User).where(User.clerk_id == clerk_id))
    if user is None:
        user = User(clerk_id=clerk_id, email=email, role=role)
        db.add(user)
        db.flush()  # gives the user its id
    return user


def _find_patient(db: Session, email: str) -> User:
    users = db.scalars(select(User).where(User.email == email)).all()
    if len(users) != 1:
        raise SeedError(
            f"Expected 1 user with that email, found {len(users)}. "
            "Sign in to the web app once first, so your user exists."
        )
    if users[0].role != Role.PATIENT:
        raise SeedError("That user is not a patient, so they can't have a plan.")
    return users[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--patient-email",
        help="give the plan to this existing patient instead of a placeholder one",
    )
    args = parser.parse_args()
    with Session(engine) as db:
        try:
            plan = seed(db, args.patient_email)
        except SeedError as exc:
            sys.exit(f"Seed failed: {exc}")
        print(f"Dev plan {plan.id} has {len(plan.exercises)} exercises.")


if __name__ == "__main__":
    main()
