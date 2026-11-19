"""Request and response models for /therapist/patients (a therapist's patients)."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints


class LinkPatientRequest(BaseModel):
    # Spaces around it are dropped and it is lowercased, so case never matters. At
    # most 320 characters, the size of users.email. No NUL character: Postgres can't
    # store or compare one, so it would fail the lookup with a 500 instead of a 422.
    email: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            to_lower=True,
            min_length=1,
            max_length=320,
            pattern=r"^[^\x00]*$",
        ),
    ]


class LinkedPatientResponse(BaseModel):
    id: uuid.UUID  # the patient's user id
    email: str
    linked_at: datetime  # when this therapist linked them
