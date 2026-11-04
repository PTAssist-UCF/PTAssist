"""Ownership checks: a therapist sees only the patients they are linked to.

Routes that show or change a patient's data for a therapist check the link with
get_link, and answer 404 when there is none, the same as for an unknown patient.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TherapistPatient


def get_link(
    db: Session, therapist_id: uuid.UUID, patient_id: uuid.UUID
) -> TherapistPatient | None:
    """This therapist's link to this patient, or None if they are not linked."""
    return db.scalar(
        select(TherapistPatient).where(
            TherapistPatient.therapist_id == therapist_id,
            TherapistPatient.patient_id == patient_id,
        )
    )
