"""The analysis contract: what the backend sends the AI service and what comes back.

THIS FILE EXISTS IN TWO PLACES, AND THE TWO MUST STAY EXACTLY THE SAME:

    ai/app/analysis_contract.py                the original: edit this one
    backend/app/schemas/analysis_contract.py   an exact copy: never edit it by hand

The AI service and the backend run in separate containers, so the backend cannot import
this file from ai/. For the same reason, this file may import only the Python standard
library and pydantic: the backend copy cannot see the AI service's other code
(app.analysis, app.keypoints) or its libraries (NumPy, OpenCV, MediaPipe). Shared
constants belong here, not the other way round.

To change the contract, edit the AI file, then copy it over (from the repo root):

    cp ai/app/analysis_contract.py backend/app/schemas/analysis_contract.py

A test in each service fails if the two files differ, and a pull request cannot merge
until the API tests pass. docs/analysis-result.md explains every field and why it is
shaped this way: update it in the same pull request.

Each class below is a Pydantic model: a list of fields with their types and limits. The
AI service uses them to check requests and to build results. The backend uses them to
check results before saving them, and its API description passes them on to the
frontend's generated types.

Results are saved in the database and kept, so old results must still load after a
change. Only add fields, and give each new field a default value. Do not rename or
remove fields, or change their types. If that is ever unavoidable, the backend also
needs a migration that rewrites the saved results (see docs/analysis-result.md).
"""

import uuid
from itertools import pairwise
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The shortest and longest videos we analyze, in seconds. Two minutes leaves time for
# patients who move slowly. The upload endpoint refuses videos outside these limits,
# and the AI service fails them with "too_short" or "too_long" as a backstop. Both
# should import these numbers, never copy them.
# The too_short and too_long messages below fill in these numbers. If you change them,
# re-read those two messages (60 would print "1 minutes"), then follow "To change" in
# decision 2 of docs/analysis-result.md: it lists the docs to update and says to
# revisit the performance target and the timeouts.
MIN_VIDEO_SECONDS = 3
MAX_VIDEO_SECONDS = 120

# Why an analysis failed. Every failure has exactly one of these codes.
ErrorCode = Literal[
    # Sent by the AI service when it cannot analyze the video.
    "video_unreadable",  # the file is damaged or is not a video
    "too_short",  # shorter than MIN_VIDEO_SECONDS
    "too_long",  # longer than MAX_VIDEO_SECONDS
    "no_person",  # nobody found in the video
    "multiple_people",  # more than one person found in the video
    "unknown_exercise",  # the AI service has no analyzer for this exercise name
    "analysis_error",  # our code crashed (a bug), or the video could not be downloaded
    # Recorded by the backend itself, when it has no valid result from the AI service.
    # The AI service could not be reached, answered with an error, or sent a result
    # that does not match this contract.
    "analysis_unavailable",
    "analysis_timed_out",  # no result in time, including sessions stuck in processing
]

# The message the patient sees for each error code: plain language that says what to do
# next. Every code above needs one (a test checks). In too_long, ":g" prints 120 / 60
# as "2", not "2.0".
ERROR_MESSAGES: dict[ErrorCode, str] = {
    "video_unreadable": (
        "We couldn't open your video. Please record it again and upload the new video."
    ),
    "too_short": (
        f"Your video is shorter than {MIN_VIDEO_SECONDS} seconds. "
        "Please record the whole exercise."
    ),
    "too_long": (
        f"Your video is longer than {MAX_VIDEO_SECONDS / 60:g} minutes. "
        "Please record a shorter video."
    ),
    "no_person": (
        "We couldn't find a person in your video. "
        "Make sure your whole body is in the frame."
    ),
    "multiple_people": (
        "We found more than one person in your video. "
        "Make sure only you are in the frame."
    ),
    "unknown_exercise": (
        "We can't check this exercise yet. Please let your therapist know."
    ),
    "analysis_error": (
        "Something went wrong while checking your video. Please upload it again."
    ),
    "analysis_unavailable": (
        "We couldn't check your video right now. Please upload it again later."
    ),
    "analysis_timed_out": (
        "Checking your video took too long. Please upload it again."
    ),
}


class AnalyzeRequest(BaseModel):
    """What the backend sends to POST /analyze."""

    # The backend's id for the upload session this video belongs to. The analysis does
    # not need it, and we do not send it back: the backend already knows which session
    # it asked about. It is useful for labelling log lines.
    session_id: uuid.UUID
    # Which exercise the patient recorded, for example "squat". It decides which
    # analyzer runs. It is a plain string, not a fixed list, so exercises can be added
    # or renamed without changing this file. An unknown name fails with
    # "unknown_exercise".
    exercise: str
    # A temporary, read-only link to the video in storage, valid for about 15 minutes.
    # Never log it: anyone who has the link can watch the video until it expires.
    video_url: str


class Issue(BaseModel):
    """A form problem seen during one rep or hold."""

    # A short snake_case code for the problem, such as "knees_cave_in". Each exercise's
    # spec in docs/ lists its codes. Any string is allowed, so adding a new form check
    # does not change this file.
    code: str
    # What went wrong, in plain language, such as "Your knees moved inward."
    message: str


class RepResult(BaseModel):
    """One rep. For a hold exercise such as the plank, one unbroken hold."""

    # Reject NaN and infinity in the number fields. JSON cannot hold them (they would be
    # sent as null), so the backend would reject the result.
    model_config = ConfigDict(allow_inf_nan=False)

    # 1 for the first rep (or hold), 2 for the second, and so on, in the order they
    # started.
    index: int = Field(ge=1)
    # When the rep (or hold) started and ended, in seconds from the start of the video.
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    # Which side of the body did the rep: "left", "right", "both" (for example both
    # arms at once), or None when sides do not apply (such as squats and planks).
    side: Literal["left", "right", "both"] | None
    # Form score for this rep (or hold): 0 (poor) to 100 (perfect).
    score: int = Field(ge=0, le=100)
    # Form problems seen during this rep (or hold). Empty if none.
    issues: list[Issue]
    # Extra measurements for this exercise, such as {"min_knee_angle_degrees": 92.5}.
    # Each exercise's spec lists its own, and each name ends with its unit. Empty if
    # none.
    metrics: dict[str, float]

    @model_validator(mode="after")
    def check_times(self) -> Self:
        """Reject a rep that ends before it starts."""
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds must not be before start_seconds")
        return self


class AnalysisResult(BaseModel):
    """What POST /analyze sends back, and what the backend saves for every session.

    Exercises are either done in reps (such as squats) or held (such as the plank).
    A complete result sets rep_count for the first kind and hold_seconds for the
    second, never both. docs/analysis-result-examples/ has an example of every kind
    (explained in docs/analysis-result.md).
    """

    # Reject NaN and infinity, as in RepResult.
    model_config = ConfigDict(allow_inf_nan=False)

    # "complete" if the video was analyzed, "failed" if it could not be (see
    # error_code).
    status: Literal["complete", "failed"]
    # How many reps were counted, for exercises done in reps. 0 means the video was
    # fine but no full rep was seen. None for hold exercises and failed results.
    rep_count: int | None = Field(ge=0)
    # The longest unbroken hold, in seconds, for hold exercises such as the plank.
    # None for exercises done in reps and for failed results.
    hold_seconds: float | None = Field(ge=0)
    # Overall form score: 0 (poor) to 100 (perfect). None when there is nothing to
    # score (no reps or holds) and for failed results.
    form_score: int | None = Field(ge=0, le=100)
    # One entry per rep (or per unbroken hold), in the order they started. Empty if
    # none.
    reps: list[RepResult]
    # Short tips for the patient, most important first (at most 3), such as "Push
    # your knees out so they stay over your toes." Empty for failed results.
    feedback: list[str]
    # For failed results: why it failed, and the message the patient sees (the one in
    # ERROR_MESSAGES). Both None for complete results.
    error_code: ErrorCode | None
    error_message: str | None
    # Which version of our analysis code made this result, such as "0.1.0". None only
    # when the backend recorded the failure itself (analysis_unavailable or
    # analysis_timed_out), because it has no valid result from the AI service.
    analyzer_version: str | None

    @model_validator(mode="after")
    def check_fields_agree(self) -> Self:
        """Reject a result whose fields contradict each other.

        The frontend relies on these rules to decide what to show. Checking them here
        catches a broken result before it is saved, not when someone opens it.
        """
        if self.status == "failed":
            if self.error_code is None or self.error_message is None:
                raise ValueError("a failed result needs error_code and error_message")
            if (
                self.rep_count is not None
                or self.hold_seconds is not None
                or self.form_score is not None
                or self.reps
                or self.feedback
            ):
                raise ValueError(
                    "a failed result has no rep_count, hold_seconds, form_score, "
                    "reps, or feedback"
                )
            return self

        if self.error_code is not None or self.error_message is not None:
            raise ValueError("a complete result has no error_code or error_message")
        # Only the AI service makes complete results, and it always knows its version.
        if self.analyzer_version is None:
            raise ValueError("a complete result needs analyzer_version")
        # rep_count for exercises done in reps, hold_seconds for holds: exactly one.
        if (self.rep_count is None) == (self.hold_seconds is None):
            raise ValueError(
                "a complete result sets exactly one of rep_count and hold_seconds"
            )
        if self.rep_count is not None and self.rep_count != len(self.reps):
            raise ValueError("rep_count must equal the number of entries in reps")
        # hold_seconds is the longest unbroken hold (0 if none). Round the times and
        # hold_seconds to 0.1 seconds, or not at all: this allows 0.2 seconds for that.
        if self.hold_seconds is not None:
            longest = max(
                (rep.end_seconds - rep.start_seconds for rep in self.reps), default=0.0
            )
            if abs(self.hold_seconds - longest) > 0.2:
                raise ValueError(
                    "hold_seconds must equal the longest hold in reps (0 if none)"
                )
        if [rep.index for rep in self.reps] != list(range(1, len(self.reps) + 1)):
            raise ValueError("reps must be numbered 1, 2, 3, ... in order")
        # Reps are listed in the order they started. Two may overlap, for example the
        # left and right arm, so only the start times are checked.
        if any(
            later.start_seconds < earlier.start_seconds
            for earlier, later in pairwise(self.reps)
        ):
            raise ValueError("reps must be listed in the order they started")
        if (self.form_score is None) != (len(self.reps) == 0):
            raise ValueError("form_score is None exactly when reps is empty")
        return self

    @classmethod
    def failed(cls, error_code: ErrorCode, analyzer_version: str | None) -> Self:
        """A failed result with the standard patient message for error_code.

        For example, AnalysisResult.failed("no_person", analyzer_version="0.1.0").
        The backend passes analyzer_version=None for failures it records itself.
        """
        return cls(
            status="failed",
            rep_count=None,
            hold_seconds=None,
            form_score=None,
            reps=[],
            feedback=[],
            error_code=error_code,
            error_message=ERROR_MESSAGES[error_code],
            analyzer_version=analyzer_version,
        )
