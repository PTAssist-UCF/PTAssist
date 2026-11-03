"""The exercises table: the exercise library therapists build plans from."""

import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExerciseKind(StrEnum):
    REPS = "reps"  # counted in reps, such as squats
    HOLD = "hold"  # held for time, such as the plank


class Exercise(Base):
    """One exercise. The rows are added by migrations, never by hand or by the API."""

    __tablename__ = "exercises"
    __table_args__ = (CheckConstraint("kind IN ('reps', 'hold')", name="kind"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # The name the AI service knows it by, such as "squat" (docs/analysis-result.md,
    # Exercise names). Plain text, not a database enum, so adding an exercise adds a
    # row instead of changing the table. Other tables point at id, not at the name, so
    # renaming an exercise changes only this row.
    name: Mapped[str] = mapped_column(String(50), unique=True)
    # What people see, such as "Side-lying leg raise".
    display_name: Mapped[str] = mapped_column(String(100))
    # "reps" or "hold". Decides which plan targets apply (see PlanExercise).
    kind: Mapped[str] = mapped_column(String(10))
