"""The shapes of the data the AI service receives and sends back.

Each class below is a Pydantic model: a list of fields with their types. FastAPI uses
them to check every request (a request that does not match gets a 422 error saying
which field is wrong) and to turn our results into JSON.

DRAFT: SCRUM-28 sets the final result schema together with the backend and frontend
teams. Until then this follows the draft in ai/README.md. If you change a field here,
change the README example too.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """What GET /health sends back."""

    status: Literal["ok"]


class AnalyzeRequest(BaseModel):
    """What the backend sends to POST /analyze."""

    # The upload session this video belongs to. The backend uses it to know where to
    # save our result.
    session_id: uuid.UUID
    # Which exercise the patient recorded, for example "exercise_1". It decides which
    # analyzer in app/analysis/exercises/ runs.
    exercise: str
    # A temporary, read-only link to the video in storage, valid for about 15 minutes.
    # Never log it: anyone who has the link can watch the video until it expires.
    video_url: str


class RepResult(BaseModel):
    """How one repetition went."""

    # 1 for the first rep, 2 for the second, and so on.
    index: int = Field(ge=1)
    # Form score for this rep: 0 (poor) to 100 (perfect).
    score: int = Field(ge=0, le=100)
    # Form problems seen in this rep, as short codes such as "too_fast". Empty if none.
    issues: list[str]


class AnalysisResult(BaseModel):
    """What POST /analyze sends back to the backend."""

    # "complete" if the video was analyzed, "failed" if it could not be (see error).
    status: Literal["complete", "failed"]
    # How many reps were counted. 0 when the analysis failed.
    rep_count: int = Field(ge=0)
    # Overall form score: 0 (poor) to 100 (perfect). None if there is nothing to score.
    form_score: int | None = Field(ge=0, le=100)
    # One entry per counted rep, in order.
    reps: list[RepResult]
    # Plain-language tips shown to the patient, such as "Slow down on the way back up."
    feedback: list[str]
    # Why the analysis failed, for example "No person found in the video". None if it
    # did not fail.
    error: str | None
    # Which version of our analysis code made this result (see app/main.py).
    analyzer_version: str
