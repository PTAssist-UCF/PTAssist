"""The therapist_patients table: which therapist is linked to which patient."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TherapistPatient(Base):
    """One link. A therapist sees only the patients they are linked to.

    The database cannot check that therapist_id points at a therapist and patient_id at
    a patient (roles live in another table), so the linking endpoints check that.
    """

    __tablename__ = "therapist_patients"
    __table_args__ = (
        # Link the same pair only once.
        UniqueConstraint("therapist_id", "patient_id"),
        CheckConstraint("therapist_id <> patient_id", name="not_self"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    therapist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
