"""Ownership checks: a therapist sees only the patients they are linked to.

Routes that show or change a patient's data for a therapist check the link with
get_link, and answer 404 when there is none, the same as for an unknown patient.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role, TherapistPatient, User


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


def can_see_patient(db: Session, user: User, patient_id: uuid.UUID) -> bool:
    """Whether this user may see this patient's sessions, results, and progress.

    A patient may see only their own, and a therapist only the users they are linked
    to who are still patients. Both users' current roles count, because a role change
    with --force (app/promote_therapist.py) keeps links, plans, and sessions. So a
    patient sees nothing through a leftover link, a therapist no longer sees their own
    sessions from when they were a patient, and a former patient's therapists no
    longer see that history (as for plans).
    """
    if user.role == Role.PATIENT:
        return patient_id == user.id
    if user.role == Role.THERAPIST:
        if get_link(db, user.id, patient_id) is None:
            return False
        # Linked, but the link is kept when a patient is made a therapist.
        patient = db.get(User, patient_id)
        return patient is not None and patient.role == Role.PATIENT
    return False
