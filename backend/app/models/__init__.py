"""Database tables. Import every model here so Alembic autogenerate can see it."""

from app.models.base import Base
from app.models.exercise import Exercise, ExerciseKind
from app.models.plan import Plan, PlanExercise
from app.models.session import ExerciseSession, SessionResult, SessionStatus
from app.models.therapist_patient import TherapistPatient
from app.models.user import Role, User

__all__ = [
    "Base",
    "Exercise",
    "ExerciseKind",
    "ExerciseSession",
    "Plan",
    "PlanExercise",
    "Role",
    "SessionResult",
    "SessionStatus",
    "TherapistPatient",
    "User",
]
