"""GET /exercises: the exercise library that therapists build plans from."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.current_user import CurrentUser
from app.db import get_db
from app.models import Exercise
from app.schemas.exercise import ExerciseResponse

router = APIRouter(tags=["exercises"])
Database = Annotated[Session, Depends(get_db)]


@router.get("/exercises")
def list_exercises(user: CurrentUser, db: Database) -> list[ExerciseResponse]:
    """Every exercise in the library, ordered by display name. Anyone signed in."""
    # The library is the same for everyone, so there is no role or owner to check:
    # CurrentUser only makes sure the caller is signed in. Its rows come from a
    # migration, and nothing in the API changes them.
    exercises = db.scalars(
        select(Exercise).order_by(Exercise.display_name, Exercise.name)
    )
    return [ExerciseResponse.model_validate(exercise) for exercise in exercises]
