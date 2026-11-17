"""The permission grid (SCRUM-68): every route, called with no token, by the wrong role,
and by the wrong owner.

GRID has a row for every route the API serves, except the few in PUBLIC, which need no
token. test_every_route_has_a_row fails when a route has neither, so a new route needs a
row here as well as its own tests (backend/README.md, Testing).

The rules (backend/README.md, Every request):
- No valid token: 401.
- The wrong role: 403 on a route for one role. On a route both roles call, the role
  decides what the caller may see (can_see_patient), so it is 404, as for the wrong
  owner.
- The wrong owner: 404, the same answer as for an id that doesn't exist, so it never
  tells whether a patient or a session exists, or who is linked to whom.

Every call is about pat's data and is well formed (real ids, a valid body), so only who
calls can make it fail. A refused call must get the same answer as the same call about
ids that don't exist, and must change nothing in the database. Each row also says who
may make the call, and those calls must succeed: otherwise a refusal could come from a
broken request instead of from who called.
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.main import app
from app.models import (
    Base,
    Exercise,
    ExerciseSession,
    Plan,
    PlanExercise,
    Role,
    SessionResult,
    SessionStatus,
    TherapistPatient,
    User,
)
from app.uploads import VideoInfo

EXAMPLES = Path(__file__).parents[2] / "docs" / "analysis-result-examples"

# The users, by name, with their roles. A user's Clerk id is user_<name> and their email
# <name>@example.com. ther is linked to pat, and other_ther only to other_pat.
ROLES = {
    "pat": Role.PATIENT,
    "ther": Role.THERAPIST,
    "other_pat": Role.PATIENT,
    "other_ther": Role.THERAPIST,
}

# Who calls: a user, and the role changes made first. The promote script with --force
# (app/promote_therapist.py) changes a role but keeps links, plans, and sessions, so a
# role can disagree with them.
CALLERS: dict[str, tuple[str, dict[str, Role]]] = {
    "patient": ("pat", {}),  # pat, whose data every call is about
    "therapist": ("ther", {}),  # linked to pat
    "other patient": ("other_pat", {}),
    "unlinked therapist": ("other_ther", {}),
    "patient made therapist": ("pat", {"pat": Role.THERAPIST}),
    "therapist made patient": ("ther", {"ther": Role.PATIENT}),
    "therapist of a former patient": ("ther", {"pat": Role.THERAPIST}),
}


@dataclass(frozen=True)
class Ids:
    """The ids a call is about: pat's, or ones that don't exist."""

    patient_id: uuid.UUID
    session_id: uuid.UUID
    plan_exercise_id: uuid.UUID
    exercise_id: uuid.UUID  # the squat, from the library, which is nobody's

    def unknown(self) -> "Ids":
        """Ids like these, except that none of them exists (the squat still does)."""
        return Ids(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), self.exercise_id)


def no_body(ids: Ids) -> dict[str, Any]:
    return {}


def plan_body(ids: Ids) -> dict[str, Any]:
    """A whole plan to save: the squat, 10 reps, 3 sets, 3 times a week."""
    squat = {"exercise_id": str(ids.exercise_id), "reps": 10, "sets": 3}
    return {"json": {"exercises": [{**squat, "times_per_week": 3}]}}


def link_body(ids: Ids) -> dict[str, Any]:
    """Link other_pat, whom ther is not linked to yet."""
    return {"json": {"email": "other_pat@example.com"}}


def upload_body(ids: Ids) -> dict[str, Any]:
    """A video for pat's squat. A few bytes, not a real video: the tests replace the
    video check (validate_video), so they need no ffmpeg."""
    return {
        "data": {"plan_exercise_id": str(ids.plan_exercise_id)},
        "files": {"video": ("exercise.mp4", b"synthetic video bytes", "video/mp4")},
    }


@dataclass(frozen=True)
class Row:
    """One route. Each column maps callers to the status they get, or, when no caller
    fits the column, says why not."""

    allowed: dict[str, int]
    wrong_role: dict[str, int] | str
    wrong_owner: dict[str, int] | str
    body: Callable[[Ids], dict[str, Any]] = no_body
    needs_storage: bool = False  # an allowed call stores a video (in Azurite)


# The routes both roles call about a patient's data. The patient sees their own, and a
# therapist a linked user's while that user is a patient (can_see_patient).
PATIENT_DATA = Row(
    allowed={"patient": 200, "therapist": 200},
    wrong_role={"patient made therapist": 404, "therapist made patient": 404},
    wrong_owner={
        "other patient": 404,
        "unlinked therapist": 404,
        "therapist of a former patient": 404,
    },
)

GRID: dict[tuple[str, str], Row] = {
    ("GET", "/me"): Row(
        allowed={"patient": 200, "therapist": 200},
        wrong_role="Anyone signed in may call it",
        wrong_owner="No id: it answers with the caller's own user (see test_me.py)",
    ),
    ("GET", "/exercises"): Row(
        allowed={"patient": 200, "therapist": 200},
        wrong_role="Anyone signed in may call it",
        wrong_owner="The exercise library is the same for everyone",
    ),
    ("POST", "/therapist/patients"): Row(
        allowed={"therapist": 201},
        wrong_role={"patient": 403, "therapist made patient": 403},
        wrong_owner="Any therapist may link any patient by email (SCRUM-62)",
        body=link_body,
    ),
    ("GET", "/therapist/patients"): Row(
        allowed={"therapist": 200},
        wrong_role={"patient": 403, "therapist made patient": 403},
        wrong_owner="No id: it lists the caller's own links, never another's",
    ),
    ("DELETE", "/therapist/patients/{patient_id}"): Row(
        # Removing a link left over from before pat was made a therapist shows nothing.
        allowed={"therapist": 204, "therapist of a former patient": 204},
        wrong_role={"patient": 403, "therapist made patient": 403},
        wrong_owner={"unlinked therapist": 404},
    ),
    ("GET", "/therapist/patients/{patient_id}/plan"): Row(
        allowed={"therapist": 200},
        wrong_role={"patient": 403, "therapist made patient": 403},
        wrong_owner={"unlinked therapist": 404, "therapist of a former patient": 404},
    ),
    ("PUT", "/therapist/patients/{patient_id}/plan"): Row(
        allowed={"therapist": 200},
        wrong_role={"patient": 403, "therapist made patient": 403},
        wrong_owner={"unlinked therapist": 404, "therapist of a former patient": 404},
        body=plan_body,
    ),
    ("GET", "/plans/me"): Row(
        allowed={"patient": 200},
        wrong_role={"therapist": 403, "patient made therapist": 403},
        # No id: another patient gets their own plan, never pat's (they have none).
        wrong_owner={"other patient": 404, "therapist made patient": 404},
    ),
    ("POST", "/sessions"): Row(
        allowed={"patient": 201},
        wrong_role={"therapist": 403, "patient made therapist": 403},
        wrong_owner={"other patient": 404, "therapist made patient": 404},
        body=upload_body,
        needs_storage=True,
    ),
    ("GET", "/sessions/{session_id}"): PATIENT_DATA,
    ("GET", "/sessions/{session_id}/result"): PATIENT_DATA,
    ("GET", "/patients/{patient_id}/sessions"): PATIENT_DATA,
    ("GET", "/patients/{patient_id}/progress"): PATIENT_DATA,
}

# The routes that need no token, and why. Every other route must have a row in GRID.
# FastAPI adds the docs pages, which show the API description, never data.
PUBLIC = {
    ("GET", "/health"): "The liveness probe for Docker and Azure; no data",
    ("GET", "/openapi.json"): "The API description, for making the web app's hooks",
    ("GET", "/docs"): "FastAPI's interactive docs (Swagger UI)",
    ("GET", "/docs/oauth2-redirect"): "Part of FastAPI's interactive docs",
    ("GET", "/redoc"): "FastAPI's read-only docs (ReDoc)",
}


def route_id(route: tuple[str, str]) -> str:
    return " ".join(route)


def cases(column: str) -> list[Any]:
    """The tests of one column, for every row: (route, caller, status)."""
    params = []
    for route, row in GRID.items():
        callers = getattr(row, column)
        if isinstance(callers, str):  # nobody fits this column, and the row says why
            continue
        for caller, status in callers.items():
            name = f"{route_id(route)} by {caller}"
            params.append(pytest.param(route, caller, status, id=name))
    return params


def served_routes() -> set[tuple[str, str]]:
    """Every (method, path) the app answers, FastAPI's own docs pages included."""
    routes = set()
    # app.routes holds each included router as one entry. iter_route_contexts lists the
    # routes inside them, as FastAPI does to describe the API.
    for route in iter_route_contexts(app.routes):
        methods = set(route.methods or {"*"})  # "*": a mount or a websocket
        if "GET" in methods:
            methods.discard("HEAD")  # Starlette answers HEAD on its own GET routes
        routes.update((method, route.path) for method in methods)
    return routes


def role_of(caller: str) -> Role:
    """The caller's role, after their role changes."""
    name, changes = CALLERS[caller]
    return changes.get(name, ROLES[name])


@pytest.fixture
def users(db: Session) -> dict[str, User]:
    """The users in ROLES, with ther linked to pat and other_ther to other_pat."""
    users = {
        name: User(clerk_id=f"user_{name}", email=f"{name}@example.com", role=role)
        for name, role in ROLES.items()
    }
    db.add_all(users.values())
    db.flush()
    for therapist, patient in [("ther", "pat"), ("other_ther", "other_pat")]:
        db.add(
            TherapistPatient(
                therapist_id=users[therapist].id, patient_id=users[patient].id
            )
        )
    db.commit()
    return users


@pytest.fixture
def pat_ids(db: Session, users: dict[str, User]) -> Ids:
    """pat's data, which every call is about: ther's plan for pat, with the squat, and a
    complete session of it with its result."""
    squat = db.scalars(select(Exercise).where(Exercise.name == "squat")).one()
    plan = Plan(therapist_id=users["ther"].id, patient_id=users["pat"].id)
    target = PlanExercise(plan=plan, exercise=squat, reps=10, sets=3, times_per_week=3)
    result = json.loads((EXAMPLES / "squat.json").read_text(encoding="utf-8"))
    session = ExerciseSession(
        plan_exercise=target,
        status=SessionStatus.COMPLETE,
        video_key=f"sessions/{uuid.uuid4()}.mp4",
        result=SessionResult(result=result),
    )
    db.add(session)
    db.commit()
    return Ids(users["pat"].id, session.id, target.id, squat.id)


@pytest.fixture
def no_video_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refused upload is refused before its video is checked or stored."""

    def check(video: Any) -> None:
        pytest.fail("A refused upload must not get to the video check")

    monkeypatch.setattr("app.routes.sessions.validate_video", check)


def become(db: Session, users: dict[str, User], caller: str) -> str:
    """Make the caller's role changes, and return their Clerk id."""
    name, changes = CALLERS[caller]
    for changed, role in changes.items():
        users[changed].role = role
    db.commit()
    return f"user_{name}"


def call(client: TestClient, route: tuple[str, str], ids: Ids, headers: dict[str, str]):
    """Call the route about these ids, with its body if it takes one."""
    method, path = route
    url = path.format(patient_id=ids.patient_id, session_id=ids.session_id)
    return client.request(method, url, headers=headers, **GRID[route].body(ids))


def database() -> dict[str, list[str]]:
    """Every row of every table, to check that a refused call changed nothing."""
    with engine.connect() as connection:
        return {
            table.name: sorted(repr(row) for row in connection.execute(select(table)))
            for table in Base.metadata.sorted_tables
        }


# The grid stays complete


def test_every_route_has_a_row() -> None:
    """A route without a row in GRID or PUBLIC fails here, so no route is left out."""
    served = served_routes()

    missing = served - GRID.keys() - PUBLIC.keys()
    unknown = (GRID.keys() | PUBLIC.keys()) - served

    assert not missing, (
        f"These routes have no row in tests/test_permissions.py: {sorted(missing)}. "
        "Add one to GRID: who may call the route, and what the wrong role and the "
        "wrong owner get (or why nobody can be either)."
    )
    assert not unknown, f"These rows name routes the API doesn't serve: {unknown}"
    assert not GRID.keys() & PUBLIC.keys()


def test_every_row_follows_the_rules() -> None:
    """Each row says who may call the route, and what the wrong role and the wrong owner
    get, or why nobody can be either. The statuses follow the rules at the top."""
    for route, row in GRID.items():
        assert row.allowed, f"{route}: who may call it?"
        both_roles = {role_of(caller) for caller in row.allowed} == set(Role)
        for column, status in [
            (row.wrong_role, 404 if both_roles else 403),
            (row.wrong_owner, 404),
        ]:
            assert column, f"{route}: test a caller, or say why there is none"
            if isinstance(column, dict):
                assert set(column.values()) == {status}, route
                assert not column.keys() & row.allowed.keys(), route


# The grid


@pytest.mark.parametrize("route", GRID, ids=route_id)
@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer not-a-jwt"}], ids=["no token", "bad"]
)
def test_no_valid_token_gets_401(
    client, pat_ids, no_video_check, route, headers
) -> None:
    before = database()

    response = call(client, route, pat_ids, headers)

    assert response.status_code == 401
    assert database() == before


def refused(client, clerk, db, users, pat_ids, route, caller, status) -> None:
    """The caller gets this status, the same answer as about ids that don't exist, so it
    doesn't tell whether pat's data exists, and nothing changes."""
    headers = clerk.headers(become(db, users, caller))
    before = database()

    response = call(client, route, pat_ids, headers)
    unknown = call(client, route, pat_ids.unknown(), headers)

    assert response.status_code == status, response.text
    assert (unknown.status_code, unknown.json()) == (status, response.json())
    assert database() == before


@pytest.mark.parametrize(("route", "caller", "status"), cases("wrong_role"))
def test_the_wrong_role_is_refused(
    client, clerk, db, users, pat_ids, no_video_check, route, caller, status
) -> None:
    refused(client, clerk, db, users, pat_ids, route, caller, status)


@pytest.mark.parametrize(("route", "caller", "status"), cases("wrong_owner"))
def test_the_wrong_owner_is_refused(
    client, clerk, db, users, pat_ids, no_video_check, route, caller, status
) -> None:
    refused(client, clerk, db, users, pat_ids, route, caller, status)


@pytest.mark.parametrize(("route", "caller", "status"), cases("allowed"))
def test_the_right_caller_gets_through(
    client, clerk, db, users, pat_ids, monkeypatch, request, route, caller, status
) -> None:
    """The same call, by someone it is for, works. So the refusals above come from who
    called, not from a broken request or missing data."""
    if GRID[route].needs_storage:
        request.getfixturevalue("storage")  # the upload is stored in Azurite
    monkeypatch.setattr(
        "app.routes.sessions.validate_video",
        lambda video: VideoInfo(".mp4", "video/mp4"),
    )
    headers = clerk.headers(become(db, users, caller))

    response = call(client, route, pat_ids, headers)

    assert response.status_code == status, response.text


@pytest.mark.parametrize("route", PUBLIC, ids=route_id)
def test_public_routes_need_no_token(route) -> None:
    response = TestClient(app).request(*route)

    assert response.status_code == 200
