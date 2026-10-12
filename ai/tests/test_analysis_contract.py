"""Tests for the analysis contract (app/analysis_contract.py).

They check that:
- the backend's copy of the contract is still exactly the same as ours (the backend
  runs the same check),
- every example result in docs/analysis-result-examples/ matches the contract,
- the contract rejects results whose fields contradict each other.
"""

import json
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from app.analysis_contract import ERROR_MESSAGES, AnalysisResult, ErrorCode

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_ORIGINAL = REPO_ROOT / "ai" / "app" / "analysis_contract.py"
BACKEND_COPY = REPO_ROOT / "backend" / "app" / "schemas" / "analysis_contract.py"
EXAMPLES = REPO_ROOT / "docs" / "analysis-result-examples"
EXAMPLE_FILES = sorted(EXAMPLES.glob("*.json"))


def load_example(name: str) -> dict[str, Any]:
    """One example result from docs/, as a dict we can change."""
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def test_backend_copy_of_analysis_contract_matches_ai_original() -> None:
    # read_text turns Windows line endings into "\n", so only real differences count.
    ai_original = AI_ORIGINAL.read_text(encoding="utf-8")
    backend_copy = BACKEND_COPY.read_text(encoding="utf-8")

    assert backend_copy == ai_original, (
        "backend/app/schemas/analysis_contract.py must be an exact copy of "
        "ai/app/analysis_contract.py. If you changed the backend copy, make the same "
        "change in ai/app/analysis_contract.py first, because the command below "
        "overwrites the backend copy. Then, from the repo root, run: "
        "cp ai/app/analysis_contract.py backend/app/schemas/analysis_contract.py "
        "(run pytest with -vv to see the whole difference)"
    )


def test_docs_examples_folder_has_example_results() -> None:
    assert EXAMPLE_FILES, f"no example results found in {EXAMPLES}"


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda path: path.name)
def test_docs_example_is_a_valid_analysis_result(path: Path) -> None:
    result = AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))

    # A failed example shows the message the patient would really see.
    if result.error_code is not None:
        assert result.error_message == ERROR_MESSAGES[result.error_code]


def test_every_error_code_has_a_patient_message() -> None:
    assert set(ERROR_MESSAGES) == set(get_args(ErrorCode))


@pytest.mark.parametrize("error_code", get_args(ErrorCode))
def test_failed_helper_uses_the_standard_patient_message(error_code: ErrorCode) -> None:
    result = AnalysisResult.failed(error_code, analyzer_version=None)

    assert result.status == "failed"
    assert result.error_code == error_code
    assert result.error_message == ERROR_MESSAGES[error_code]


# Each case starts from an example in docs/ and changes some fields so they contradict
# each other.
CONTRADICTIONS = [
    pytest.param(
        "squat.json", {"error_code": "no_person"}, id="complete with an error code"
    ),
    pytest.param(
        "squat.json", {"hold_seconds": 30.0}, id="both rep_count and hold_seconds"
    ),
    pytest.param(
        "squat.json", {"rep_count": None}, id="neither rep_count nor hold_seconds"
    ),
    pytest.param("squat.json", {"rep_count": 5}, id="rep_count does not match reps"),
    pytest.param("squat.json", {"form_score": None}, id="reps but no form_score"),
    pytest.param(
        "squat-zero-reps.json", {"form_score": 50}, id="form_score but no reps"
    ),
    pytest.param(
        "failed-no-person.json", {"error_code": None}, id="failed with no error_code"
    ),
    pytest.param(
        "failed-no-person.json",
        {"error_message": None},
        id="failed with no error_message",
    ),
    pytest.param(
        "failed-no-person.json",
        {"error_code": "not_a_real_code"},
        id="error_code not in the list",
    ),
    pytest.param("failed-no-person.json", {"rep_count": 0}, id="failed with rep_count"),
    pytest.param(
        "failed-no-person.json", {"hold_seconds": 10.0}, id="failed with hold_seconds"
    ),
    pytest.param(
        "failed-no-person.json", {"form_score": 50}, id="failed with form_score"
    ),
    pytest.param(
        "failed-no-person.json",
        {"reps": load_example("squat.json")["reps"]},
        id="failed with reps",
    ),
    pytest.param(
        "failed-no-person.json", {"feedback": ["Nice work!"]}, id="failed with feedback"
    ),
    pytest.param(
        "squat.json", {"analyzer_version": None}, id="complete with no analyzer_version"
    ),
    pytest.param(
        "plank.json", {"hold_seconds": 34.5}, id="hold_seconds is the total hold time"
    ),
    pytest.param(
        "plank-no-hold.json", {"hold_seconds": 5.0}, id="hold_seconds but no holds"
    ),
    pytest.param("squat.json", {"form_score": float("nan")}, id="form_score is NaN"),
    pytest.param("plank.json", {"hold_seconds": float("inf")}, id="hold is infinite"),
]


@pytest.mark.parametrize(("example", "changes"), CONTRADICTIONS)
def test_result_with_contradicting_fields_is_rejected(
    example: str, changes: dict
) -> None:
    result = {**load_example(example), **changes}

    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(result)


def test_hold_seconds_rounded_within_tolerance_is_accepted() -> None:
    # The longest hold in plank.json is 22.0 seconds. The contract allows 0.2 seconds
    # of difference, because times are rounded to 0.1 seconds.
    result = load_example("plank.json")
    result["hold_seconds"] = 22.1

    AnalysisResult.model_validate(result)


def test_rep_that_ends_before_it_starts_is_rejected() -> None:
    result = load_example("squat.json")
    result["reps"][0]["end_seconds"] = result["reps"][0]["start_seconds"] - 1

    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(result)


def test_reps_numbered_out_of_order_are_rejected() -> None:
    result = load_example("squat.json")
    result["reps"][0]["index"], result["reps"][1]["index"] = 2, 1

    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(result)


def test_reps_listed_out_of_time_order_are_rejected() -> None:
    result = load_example("squat.json")
    first, second = result["reps"][0], result["reps"][1]
    first["start_seconds"], second["start_seconds"] = (
        second["start_seconds"],
        first["start_seconds"],
    )
    first["end_seconds"], second["end_seconds"] = (
        second["end_seconds"],
        first["end_seconds"],
    )

    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(result)


def test_nan_metric_value_is_rejected() -> None:
    # NaN cannot be written as JSON, so it must never get into a result.
    result = load_example("squat.json")
    result["reps"][0]["metrics"]["min_knee_angle_degrees"] = float("nan")

    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(result)
