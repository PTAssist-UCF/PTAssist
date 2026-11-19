"""Response model for GET /exercises: the exercise library."""

import uuid

from pydantic import BaseModel, ConfigDict

from app.models import ExerciseKind


class ExerciseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID  # what a plan points at: the exercise_id when saving a plan
    name: str  # the AI service's name for it, such as "squat"
    display_name: str  # what people see, such as "Squat"
    kind: ExerciseKind  # "reps", or "hold" for an exercise held for time (the plank)
