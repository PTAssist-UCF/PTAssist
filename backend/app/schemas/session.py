"""Upload acknowledgement and pollable status; storage keys remain private."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import SessionStatus


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_exercise_id: uuid.UUID
    status: SessionStatus
    created_at: datetime
