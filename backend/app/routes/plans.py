"""Plans: a therapist saves a linked patient's plan, and the patient reads their own.

A plan is a list of exercises from the library, each with its targets (a PlanExercise).
A patient has one plan, and every therapist linked to them can see and change it. The
rules, and why, are in backend/README.md, Exercise library and plans (SCRUM-63).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.current_user import CurrentTherapist, CurrentUser
from app.auth.ownership import get_link
from app.db import get_db
from app.models import (
    Exercise,
    ExerciseKind,
    ExerciseSession,
    Plan,
    PlanExercise,
    Role,
    User,
)
from app.schemas.plan import PlanExerciseResponse, PlanResponse, SavePlanRequest

router = APIRouter(tags=["plans"])
Database = Annotated[Session, Depends(get_db)]


@router.get("/therapist/patients/{patient_id}/plan")
def get_patient_plan(
    patient_id: uuid.UUID, therapist: CurrentTherapist, db: Database
) -> PlanResponse:
    """A linked patient's plan. 404 if they have none yet."""
    patient = _find_linked_patient(db, therapist, patient_id)
    plan = _find_plan(db, patient.id)
    if plan is None:
        # Only for a linked patient, so it tells the caller nothing about anyone else.
        raise HTTPException(404, "This patient has no plan yet")
    return _plan_response(db, plan)


@router.put(
    "/therapist/patients/{patient_id}/plan",
    responses={201: {"model": PlanResponse, "description": "The plan was created"}},
)
def save_patient_plan(
    patient_id: uuid.UUID,
    body: SavePlanRequest,
    therapist: CurrentTherapist,
    db: Database,
    response: Response,
) -> PlanResponse:
    """Save a linked patient's whole plan: create it (201), or replace its exercises and
    targets (200). An exercise the patient has uploaded videos for can't be left out."""
    patient = _find_linked_patient(db, therapist, patient_id)
    _check_exercises(db, body)
    # Saves for one patient run one at a time: each locks the patient's row until it
    # ends. The database allows a patient several plans, so without the lock two saves
    # at once could both find no plan and make one each.
    db.execute(select(User.id).where(User.id == patient.id).with_for_update())
    plan = _find_plan(db, patient.id)
    created = plan is None
    if plan is None:
        plan = Plan(therapist_id=therapist.id, patient_id=patient.id)
        db.add(plan)
        db.flush()  # gives the plan its id
    # The plan's exercises, by exercise. FOR UPDATE: an upload saving a session for one
    # of them right now waits until this save ends, so the check below can't miss it.
    current = {
        item.exercise_id: item
        for item in db.scalars(
            select(PlanExercise)
            .where(PlanExercise.plan_id == plan.id)
            .with_for_update()
        )
    }
    sent = {target.exercise_id for target in body.exercises}
    left_out = [item for item in current.values() if item.exercise_id not in sent]
    uploaded = _with_sessions(db, left_out)
    if uploaded:
        # Results are kept, and a plan exercise with sessions can't be deleted (the
        # database refuses). Nothing has changed: the transaction is rolled back.
        names = ", ".join(sorted(item.exercise.display_name for item in uploaded))
        raise HTTPException(
            409,
            "Nothing was saved. These exercises can't be removed from the plan, "
            "because the patient has uploaded videos for them and their results are "
            f"kept: {names}. You can change their targets instead.",
        )
    for item in left_out:
        db.delete(item)  # no uploads, so nothing is lost
    for target in body.exercises:
        item = current.get(target.exercise_id)
        if item is None:  # an exercise the plan didn't have yet
            item = PlanExercise(plan_id=plan.id, exercise_id=target.exercise_id)
            db.add(item)
        # An exercise the plan had is changed in place: it keeps its id, and with it
        # its sessions, their results, and the patient's upload link.
        item.reps = target.reps
        item.hold_seconds = target.hold_seconds
        item.sets = target.sets
        item.times_per_week = target.times_per_week
    db.flush()  # write the changes, so the answer below reads them back
    saved = _plan_response(db, plan)
    db.commit()
    if created:
        response.status_code = 201
    return saved


@router.get("/plans/me")
def get_my_plan(user: CurrentUser, db: Database) -> PlanResponse:
    """The signed-in patient's own plan. 404 if they have none yet."""
    if user.role != Role.PATIENT:
        raise HTTPException(403, "Only patients have a plan")
    plan = _find_plan(db, user.id)
    if plan is None:
        raise HTTPException(
            404, "You don't have a plan yet. Your therapist will make one for you."
        )
    return _plan_response(db, plan)


def _find_linked_patient(db: Session, therapist: User, patient_id: uuid.UUID) -> User:
    """The patient, if the therapist is linked to them. Otherwise 404, the same answer
    as for an unknown id, so it doesn't tell who is linked to whom."""
    link = get_link(db, therapist.id, patient_id)
    patient = db.get(User, patient_id) if link else None
    # Also 404 for a linked user who is no longer a patient (made a therapist since):
    # only patients have plans.
    if patient is None or patient.role != Role.PATIENT:
        raise HTTPException(404, "Patient not found")
    return patient


def _find_plan(db: Session, patient_id: uuid.UUID) -> Plan | None:
    """The patient's plan, or None. The API makes at most one plan per patient; if
    older data has more, the newest is the one used."""
    return db.scalar(
        select(Plan)
        .where(Plan.patient_id == patient_id)
        .order_by(Plan.created_at.desc(), Plan.id)
        .limit(1)
    )


def _check_exercises(db: Session, body: SavePlanRequest) -> None:
    """422 unless every exercise sent is in the library and has the target its kind
    needs: reps for an exercise done in reps, hold_seconds for one held for time. The
    database can't check the kind, because it is in another table."""
    ids = [target.exercise_id for target in body.exercises]
    library = {
        exercise.id: exercise
        for exercise in db.scalars(select(Exercise).where(Exercise.id.in_(ids)))
    }
    for target in body.exercises:
        exercise = library.get(target.exercise_id)
        if exercise is None:
            raise HTTPException(422, f"No exercise has the id {target.exercise_id}")
        if exercise.kind == ExerciseKind.HOLD and target.hold_seconds is None:
            raise HTTPException(
                422,
                f"{exercise.display_name} is held for time, so its target is "
                "hold_seconds, not reps",
            )
        if exercise.kind == ExerciseKind.REPS and target.reps is None:
            raise HTTPException(
                422,
                f"{exercise.display_name} is done in reps, so its target is reps, "
                "not hold_seconds",
            )


def _with_sessions(db: Session, items: list[PlanExercise]) -> list[PlanExercise]:
    """The plan exercises that have at least one session (an uploaded video)."""
    if not items:
        return []
    used = set(
        db.scalars(
            select(ExerciseSession.plan_exercise_id).where(
                ExerciseSession.plan_exercise_id.in_([item.id for item in items])
            )
        )
    )
    return [item for item in items if item.id in used]


def _plan_response(db: Session, plan: Plan) -> PlanResponse:
    """The plan with its exercises, in the same order as GET /exercises."""
    items = db.scalars(
        select(PlanExercise)
        .join(PlanExercise.exercise)
        .where(PlanExercise.plan_id == plan.id)
        .order_by(Exercise.display_name, Exercise.name)
    )
    return PlanResponse(
        id=plan.id,
        patient_id=plan.patient_id,
        created_at=plan.created_at,
        exercises=[PlanExerciseResponse.model_validate(item) for item in items],
    )
