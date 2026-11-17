"""Ownership checks: a therapist sees only the patients they are linked to.

Routes that show or change a patient's data for a therapist check the link with
get_link, and answer 404 when there is none, the same as for an unknown patient.
"""

import uuid
from datetime import datetime

from sqlalchemy import Select, select
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


def linked_patients(therapist_id: uuid.UUID) -> Select[tuple[User, datetime]]:
    """The users this therapist sees, each with when they were linked: the users they
    are linked to who are still patients.

    A link alone is not enough, because a role change with --force
    (app/promote_therapist.py) keeps it. A linked user made a therapist is left out,
    until they are made a patient again. The therapist's list of patients and
    can_see_patient both use this rule.
    """
    return (
        select(User, TherapistPatient.created_at)
        .join(TherapistPatient, TherapistPatient.patient_id == User.id)
        .where(
            TherapistPatient.therapist_id == therapist_id,
            User.role == Role.PATIENT,
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
        visible = linked_patients(user.id).where(User.id == patient_id)
        return db.execute(visible).first() is not None
    return False
