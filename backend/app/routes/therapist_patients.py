"""/therapist/patients: a therapist links patients by email, lists, and unlinks them.

Therapists only. Each therapist sees and changes only their own links.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth.current_user import CurrentTherapist
from app.auth.ownership import get_link
from app.db import get_db
from app.models import Role, TherapistPatient, User
from app.schemas.therapist_patient import LinkedPatientResponse, LinkPatientRequest

router = APIRouter(tags=["patients"])
Database = Annotated[Session, Depends(get_db)]


@router.post("/therapist/patients", status_code=201)
def link_patient(
    body: LinkPatientRequest, therapist: CurrentTherapist, db: Database
) -> LinkedPatientResponse:
    """Link an existing patient by the email they signed in with."""
    # body.email is already lowercase. lower() and =, not ILIKE: ILIKE would treat the
    # "_" and "%" that emails can contain as wildcards and match other addresses.
    patients = db.scalars(
        select(User).where(
            func.lower(User.email) == body.email, User.role == Role.PATIENT
        )
    ).all()
    if not patients:
        # The same answer when a therapist has this email (the caller included, so
        # nobody can link themselves): it doesn't tell who has an account.
        raise HTTPException(
            404,
            "No patient uses that email. They need to sign in to PTAssist once "
            "before you can link them.",
        )
    if len(patients) > 1:
        # Our copy of an email can be out of date, so two patients can share one.
        # Never guess: linking the wrong one would show a stranger's data.
        raise HTTPException(
            409,
            "More than one patient uses that email, so it can't be linked. "
            "Ask the team to check it.",
        )
    patient = patients[0]
    # The database refuses a second link for the same pair. ON CONFLICT DO NOTHING
    # turns that into no row, so linking twice (even two requests at once) is a 409.
    link = db.scalar(
        insert(TherapistPatient)
        .values(therapist_id=therapist.id, patient_id=patient.id)
        .on_conflict_do_nothing(
            index_elements=[TherapistPatient.therapist_id, TherapistPatient.patient_id]
        )
        .returning(TherapistPatient)
    )
    if link is None:
        raise HTTPException(409, "That patient is already linked to you")
    # Before the commit, which expires the loaded rows (reading them again is a query).
    response = LinkedPatientResponse(
        id=patient.id, email=patient.email, linked_at=link.created_at
    )
    db.commit()
    return response


@router.get("/therapist/patients")
def list_linked_patients(
    therapist: CurrentTherapist, db: Database
) -> list[LinkedPatientResponse]:
    """The caller's linked patients, ordered by email. Never another therapist's."""
    rows = db.execute(
        select(User, TherapistPatient.created_at)
        .join(TherapistPatient, TherapistPatient.patient_id == User.id)
        .where(TherapistPatient.therapist_id == therapist.id)
        .order_by(User.email, User.id)
    )
    return [
        LinkedPatientResponse(id=patient.id, email=patient.email, linked_at=linked_at)
        for patient, linked_at in rows
    ]


@router.delete("/therapist/patients/{patient_id}", status_code=204)
def unlink_patient(
    patient_id: uuid.UUID, therapist: CurrentTherapist, db: Database
) -> None:
    """Remove the caller's link to this patient. Plans and sessions are kept."""
    link = get_link(db, therapist.id, patient_id)
    if link is None:
        # Also another therapist's patient: 404, so it doesn't say who is linked.
        raise HTTPException(404, "Patient not found")
    db.delete(link)
    db.commit()
