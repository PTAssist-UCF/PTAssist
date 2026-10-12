"""Response shapes used only by the AI service itself.

The shapes the AI service shares with the backend (the POST /analyze request and its
result) live in app/analysis_contract.py instead, because the backend keeps an exact
copy of that file.

Each class below is a Pydantic model: a list of fields with their types. FastAPI uses
them to turn our responses into JSON.
"""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """What GET /health sends back."""

    status: Literal["ok"]
