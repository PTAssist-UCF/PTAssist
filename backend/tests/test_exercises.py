"""Tests for GET /exercises: the exercise library.

The library is the same for everyone signed in, so there is no wrong role or wrong owner
to test: both roles get it, and nobody without a valid token does.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import Exercise, Role, User


@pytest.fixture
def users(db: Session) -> None:
    """A therapist (Clerk id user_ther) and a patient (user_pat)."""
    db.add_all(
        [
            User(clerk_id="user_ther", email="ther@example.com", role=Role.THERAPIST),
            User(clerk_id="user_pat", email="pat@example.com", role=Role.PATIENT),
        ]
    )
    db.commit()


@pytest.mark.parametrize("user", ["user_ther", "user_pat"])
def test_anyone_signed_in_gets_the_library(client, clerk, db, users, user) -> None:
    response = client.get("/exercises", headers=clerk.headers(user))

    assert response.status_code == 200
    rows = {row.name: row for row in db.scalars(select(Exercise))}
    # The five exercises the migration adds, ordered by the name people see.
    assert [exercise["display_name"] for exercise in response.json()] == [
        "Cat-cow",
        "Plank",
        "Shoulder abduction",
        "Side-lying leg raise",
        "Squat",
    ]
    for exercise in response.json():
        row = rows[exercise["name"]]
        assert exercise == {
            "id": str(row.id),
            "name": row.name,
            "display_name": row.display_name,
            "kind": row.kind,
        }


def test_the_plank_is_the_only_hold(client, clerk, users) -> None:
    """kind tells the plan builder which target to ask for: reps, or a hold time."""
    response = client.get("/exercises", headers=clerk.headers("user_pat"))

    kinds = {exercise["name"]: exercise["kind"] for exercise in response.json()}
    assert kinds == {
        "cat_cow": "reps",
        "plank": "hold",
        "shoulder_abduction": "reps",
        "side_leg_raise": "reps",
        "squat": "reps",
    }


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer not-a-jwt"}], ids=["no token", "bad"]
)
def test_no_valid_token_gets_401(client, db, headers) -> None:
    response = client.get("/exercises", headers=headers)

    assert response.status_code == 401


def test_openapi_names_the_frontend_hook() -> None:
    """The frontend's generated hook is named after it: useListExercises()."""
    operation = app.openapi()["paths"]["/exercises"]["get"]

    assert (operation["operationId"], operation["tags"]) == (
        "list_exercises",
        ["exercises"],
    )
