"""The plans and plan_exercises tables: what a therapist asks a patient to do."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.exercise import Exercise


class Plan(Base):
    """A therapist's plan for one patient: a list of exercises with targets."""

    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    therapist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    exercises: Mapped[list["PlanExercise"]] = relationship(back_populates="plan")


class PlanExercise(Base):
    """One exercise in a plan, with its targets.

    An exercise done in reps has a target of reps per set. A hold exercise (the plank)
    has a target hold time in seconds instead. Both have a number of sets, and one
    uploaded video is one set, so sets is how many videos to upload each time.

    The database checks that exactly one of reps and hold_seconds is set. It cannot
    check that it is the right one for the exercise's kind (that is in another table),
    so the plan endpoints check that.
    """

    __tablename__ = "plan_exercises"
    __table_args__ = (
        # Each exercise appears in a plan at most once.
        UniqueConstraint("plan_id", "exercise_id"),
        CheckConstraint(
            "(reps IS NULL) <> (hold_seconds IS NULL)", name="reps_or_hold_seconds"
        ),
        # A check fails only when it is false, so a null reps or hold_seconds passes.
        CheckConstraint("reps > 0 AND hold_seconds > 0", name="target_positive"),
        CheckConstraint("sets > 0", name="sets_positive"),
        CheckConstraint("times_per_week BETWEEN 1 AND 7", name="times_per_week"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id"))
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id"))
    # Reps per set, for exercises done in reps. None for hold exercises.
    reps: Mapped[int | None]
    # Target hold time per set, in seconds, for hold exercises. None for reps.
    hold_seconds: Mapped[int | None]
    # Sets each time the patient does the exercise. One video is one set.
    sets: Mapped[int]
    # How many days a week to do the exercise.
    times_per_week: Mapped[int]

    plan: Mapped[Plan] = relationship(back_populates="exercises")
    exercise: Mapped[Exercise] = relationship()
