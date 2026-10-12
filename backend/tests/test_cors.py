"""Tests for browser access (CORS): only the web app's origins may call the API.

conftest.py sets CLERK_AUTHORIZED_PARTIES to WEB_APP_ORIGIN (http://localhost:5173),
the Vite dev server, so that is the only origin allowed here.
"""

from fastapi.testclient import TestClient

from app.main import app

WEB_APP_ORIGIN = "http://localhost:5173"
OTHER_ORIGIN = "https://evil.example"

client = TestClient(app)


def preflight(origin: str):
    """The question a browser asks before sending GET /me with a token."""
    return client.options(
        "/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )


def test_web_app_may_send_a_token_to_the_api() -> None:
    response = preflight(WEB_APP_ORIGIN)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEB_APP_ORIGIN
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed_headers
    assert "GET" in response.headers["access-control-allow-methods"]
    # The token is a header, not a cookie, so cookies are never allowed.
    assert "access-control-allow-credentials" not in response.headers


def test_other_websites_may_not_call_the_api() -> None:
    response = preflight(OTHER_ORIGIN)

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_answers_name_the_web_app_as_allowed() -> None:
    response = client.get("/health", headers={"Origin": WEB_APP_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEB_APP_ORIGIN


def test_answers_to_other_websites_are_not_shared() -> None:
    # The API still answers, but without the header the browser hides the answer
    # from the other website's page.
    response = client.get("/health", headers={"Origin": OTHER_ORIGIN})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_error_answers_also_reach_the_web_app() -> None:
    # A 401 must reach the web app as a 401 (so it can send the user to sign in),
    # not as a browser "Failed to fetch".
    response = client.get("/me", headers={"Origin": WEB_APP_ORIGIN})

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == WEB_APP_ORIGIN
