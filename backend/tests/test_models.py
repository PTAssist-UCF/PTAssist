"""Tests for the core data model: the exercise library and the rules the database
enforces on its own (constraints), so bad rows are refused even if an endpoint forgets
to check."""

import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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


def add_user(db: Session, name: str, role: Role) -> User:
    user = User(clerk_id=f"user_{name}", email=f"{name}@example.com", role=role)
    db.add(user)
    db.flush()
    return user


def exercise(db: Session, name: str) -> Exercise:
    return db.scalars(select(Exercise).where(Exercise.name == name)).one()


@pytest.fixture
def plan(db: Session) -> Plan:
    """A therapist's empty plan for a linked patient."""
    therapist = add_user(db, "ther", Role.THERAPIST)
    patient = add_user(db, "pat", Role.PATIENT)
    db.add(TherapistPatient(therapist_id=therapist.id, patient_id=patient.id))
    plan = Plan(therapist_id=therapist.id, patient_id=patient.id)
    db.add(plan)
    db.commit()
    return plan


def add_session(db: Session, plan: Plan) -> ExerciseSession:
    plan_exercise = PlanExercise(
        plan=plan, exercise=exercise(db, "squat"), reps=10, sets=3, times_per_week=3
    )
    session = ExerciseSession(
        plan_exercise=plan_exercise, status=SessionStatus.PROCESSING
    )
    db.add(session)
    db.commit()
    return session


def test_the_migration_adds_the_five_exercises(db: Session) -> None:
    kinds = {row.name: row.kind for row in db.scalars(select(Exercise))}

    # The names the AI service knows (docs/analysis-result.md, Exercise names).
    assert kinds == {
        "plank": ExerciseKind.HOLD,
        "shoulder_abduction": ExerciseKind.REPS,
        "side_leg_raise": ExerciseKind.REPS,
        "squat": ExerciseKind.REPS,
        "cat_cow": ExerciseKind.REPS,
    }


def test_exercise_kind_must_be_reps_or_hold(db: Session) -> None:
    db.add(Exercise(name="lunge", display_name="Lunge", kind="sets"))

    with pytest.raises(IntegrityError, match="ck_exercises_kind"):
        db.flush()


def test_a_rep_target_and_a_hold_target_are_both_accepted(
    db: Session, plan: Plan
) -> None:
    squat, plank = exercise(db, "squat"), exercise(db, "plank")
    db.add_all(
        [
            PlanExercise(
                plan=plan,
                exercise=squat,
                reps=10,
                sets=3,
                times_per_week=3,
            ),
            PlanExercise(
                plan=plan,
                exercise=plank,
                hold_seconds=30,
                sets=3,
                times_per_week=3,
            ),
        ]
    )
    db.commit()

    assert len(plan.exercises) == 2


@pytest.mark.parametrize(
    ("targets", "constraint"),
    [
        ({"reps": 10, "hold_seconds": 30}, "reps_or_hold_seconds"),
        ({}, "reps_or_hold_seconds"),
        ({"reps": 0}, "target_positive"),
        ({"hold_seconds": -5}, "target_positive"),
        ({"reps": 10, "sets": 0}, "sets_positive"),
        ({"reps": 10, "times_per_week": 0}, "times_per_week"),
        ({"reps": 10, "times_per_week": 8}, "times_per_week"),
    ],
    ids=[
        "both reps and hold",
        "neither reps nor hold",
        "zero reps",
        "negative hold",
        "zero sets",
        "zero times a week",
        "eight times a week",
    ],
)
def test_bad_plan_targets_are_refused(
    db: Session, plan: Plan, targets: dict[str, int], constraint: str
) -> None:
    db.add(
        PlanExercise(
            plan=plan,
            exercise=exercise(db, "squat"),
            **{"sets": 3, "times_per_week": 3, **targets},
        )
    )

    with pytest.raises(IntegrityError, match=f"ck_plan_exercises_{constraint}"):
        db.flush()


def test_an_exercise_is_in_a_plan_only_once(db: Session, plan: Plan) -> None:
    for _ in range(2):
        db.add(
            PlanExercise(
                plan=plan,
                exercise=exercise(db, "squat"),
                reps=10,
                sets=3,
                times_per_week=3,
            )
        )

    with pytest.raises(IntegrityError, match="uq_plan_exercises_plan_id_exercise_id"):
        db.flush()


def test_a_pair_is_linked_only_once(db: Session, plan: Plan) -> None:
    db.add(TherapistPatient(therapist_id=plan.therapist_id, patient_id=plan.patient_id))

    with pytest.raises(IntegrityError, match="uq_therapist_patients"):
        db.flush()


def test_a_user_cannot_be_linked_to_themselves(db: Session) -> None:
    therapist = add_user(db, "ther", Role.THERAPIST)
    db.add(TherapistPatient(therapist_id=therapist.id, patient_id=therapist.id))

    with pytest.raises(IntegrityError, match="ck_therapist_patients_not_self"):
        db.flush()


def test_session_status_must_be_a_known_one(db: Session, plan: Plan) -> None:
    session = add_session(db, plan)
    session.status = "done"

    with pytest.raises(IntegrityError, match="ck_sessions_status"):
        db.flush()


def test_a_session_has_at_most_one_result(db: Session, plan: Plan) -> None:
    session_id = add_session(db, plan).id
    failed = AnalysisResult.failed("analysis_timed_out", analyzer_version=None)
    db.add(SessionResult(session_id=session_id, result=failed.model_dump(mode="json")))
    db.commit()
    db.expunge_all()  # forget the saved result, so the second one goes to the database

    db.add(SessionResult(session_id=session_id, result=failed.model_dump(mode="json")))
    with pytest.raises(IntegrityError, match="pk_session_results"):
        db.flush()


@pytest.mark.parametrize(
    "example", sorted(EXAMPLES.glob("*.json")), ids=lambda p: p.stem
)
def test_a_result_reads_back_exactly_as_saved(
    db: Session, plan: Plan, example: Path
) -> None:
    """Every example in docs/analysis-result-examples/ survives the JSONB column."""
    result = AnalysisResult.model_validate_json(example.read_text())
    session = add_session(db, plan)
    session.status = result.status
    db.add(SessionResult(session_id=session.id, result=result.model_dump(mode="json")))
    db.commit()
    db.expire_all()  # read it back from the database, not from memory

    saved = db.get(SessionResult, session.id)
    assert AnalysisResult.model_validate(saved.result) == result
    assert saved.result == json.loads(example.read_text())


def test_a_plan_exercise_with_sessions_cannot_be_deleted(
    db: Session, plan: Plan
) -> None:
    """Deleting it would lose the patient's results."""
    session = add_session(db, plan)
    db.delete(session.plan_exercise)

    with pytest.raises(IntegrityError, match="fk_sessions_plan_exercise_id"):
        db.flush()
