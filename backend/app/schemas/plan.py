"""Request and response models for plans: the exercises a therapist asks a patient to
do, each with targets."""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.analysis_contract import MAX_VIDEO_SECONDS
from app.schemas.exercise import ExerciseResponse

# Upper limits for the targets. They catch typos (100 instead of 10) and keep numbers in
# the range the database columns hold. Sanity checks, not clinical advice.
MAX_REPS = 100
MAX_SETS = 10
# One video is one set, so a hold has to fit in one clip.
MAX_HOLD_SECONDS = MAX_VIDEO_SECONDS


class PlanExerciseRequest(BaseModel):
    """One exercise of the plan and its targets. An exercise done in reps gets reps (per
    set); one held for time, the plank, gets hold_seconds instead. Never both."""

    exercise_id: uuid.UUID  # from GET /exercises
    reps: Annotated[int, Field(ge=1, le=MAX_REPS)] | None = None
    hold_seconds: Annotated[int, Field(ge=1, le=MAX_HOLD_SECONDS)] | None = None
    # One video is one set, so this is how many videos to upload each time.
    sets: Annotated[int, Field(ge=1, le=MAX_SETS)]
    # How many days a week to do the exercise.
    times_per_week: Annotated[int, Field(ge=1, le=7)]

    @model_validator(mode="after")
    def check_one_target(self) -> Self:
        # Which of the two fits the exercise is checked by the route, which looks up the
        # exercise's kind in the library.
        if (self.reps is None) == (self.hold_seconds is None):
            raise ValueError("Give either reps or hold_seconds, not both or neither")
        return self


class SavePlanRequest(BaseModel):
    """The whole plan. Saving it replaces the exercises and targets the plan had."""

    exercises: Annotated[list[PlanExerciseRequest], Field(min_length=1)]

    @field_validator("exercises")
    @classmethod
    def check_each_exercise_once(
        cls, exercises: list[PlanExerciseRequest]
    ) -> list[PlanExerciseRequest]:
        # The database also refuses an exercise twice in a plan, but with a 500.
        ids = [exercise.exercise_id for exercise in exercises]
        if len(set(ids)) < len(ids):
            raise ValueError("Each exercise can be in the plan only once")
        return exercises


class PlanExerciseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID  # the plan_exercise_id that POST /sessions takes with a video
    exercise: ExerciseResponse
    reps: int | None  # None for an exercise held for time
    hold_seconds: int | None  # None for an exercise done in reps
    sets: int
    times_per_week: int


class PlanResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    created_at: datetime
    exercises: list[PlanExerciseResponse]  # in the same order as GET /exercises
