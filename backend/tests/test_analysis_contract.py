"""Checks the backend's copy of the analysis contract.

app/schemas/analysis_contract.py is an exact copy of ai/app/analysis_contract.py, which
the AI service owns (see the top of that file). The first test fails when someone
changes one file without the other. This job must pass before a pull request can merge,
so the two cannot drift apart on main. The AI service runs the same check.
"""

from pathlib import Path

import pytest

from app.schemas.analysis_contract import AnalysisResult

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_ORIGINAL = REPO_ROOT / "ai" / "app" / "analysis_contract.py"
BACKEND_COPY = REPO_ROOT / "backend" / "app" / "schemas" / "analysis_contract.py"
EXAMPLES = REPO_ROOT / "docs" / "analysis-result-examples"
EXAMPLE_FILES = sorted(EXAMPLES.glob("*.json"))


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
    # The examples in docs/ are the results the frontend is built against. The backend
    # runs its own library versions, so check it loads every one of them too.
    AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
