"""Tests for the API description (OpenAPI), which the frontend's hooks are made from."""

from collections import Counter

from app.main import app


def operation_ids() -> list[str]:
    spec = app.openapi()
    return [
        operation["operationId"]
        for path in spec["paths"].values()
        for operation in path.values()
    ]


def test_operation_ids_are_the_route_function_names() -> None:
    # The frontend hook for GET /me is named after this id: useGetMe().
    assert app.openapi()["paths"]["/me"]["get"]["operationId"] == "get_me"


def test_operation_ids_are_unique() -> None:
    # Two routes with the same function name would give two hooks the same name.
    duplicates = [name for name, count in Counter(operation_ids()).items() if count > 1]
    assert duplicates == [], f"route function names used twice: {duplicates}"
