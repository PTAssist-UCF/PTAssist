"""Tests for app/storage against real Azurite: uploads, read links, and deletes."""

import base64
import logging
import os
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from azure.storage.blob import BlobServiceClient

from app.storage import blob
from app.storage.blob import Storage

VIDEO = b"\x00\x00\x00\x18ftypmp42 not a real video"


def new_key() -> str:
    """A key no other test uses, since all tests share one container."""
    return f"sessions/{uuid.uuid4()}.mp4"


def without_signature(link: str) -> str:
    return link.split("?", 1)[0]


def error_code(response: httpx.Response) -> str | None:
    return response.headers.get("x-ms-error-code")


def azure_style_storage() -> Storage:
    """Storage for a made-up https account, like Azure's. Only for signing links."""
    fake_key = base64.b64encode(b"fake account key for tests").decode()
    return Storage(
        "DefaultEndpointsProtocol=https;AccountName=ptassisttest;"
        f"AccountKey={fake_key};EndpointSuffix=core.windows.net",
        "videos",
    )


def test_read_link_returns_the_uploaded_file(storage: Storage) -> None:
    key = new_key()
    storage.upload(key, VIDEO, "video/mp4")

    response = httpx.get(storage.read_url(key))

    assert response.status_code == 200
    assert response.content == VIDEO
    assert response.headers["content-type"] == "video/mp4"


def test_upload_from_a_file_object(
    storage: Storage, blob_service: BlobServiceClient
) -> None:
    """Like FastAPI's UploadFile.file. Over 4 MB, so it goes up in 4 MB blocks."""
    data = os.urandom(5 * 1024 * 1024)
    key = new_key()
    with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as file:
        file.write(data)
        file.seek(0)
        storage.upload(key, file, "video/mp4")

    response = httpx.get(storage.read_url(key))

    assert response.status_code == 200
    assert response.content == data
    blob_client = blob_service.get_blob_client(os.environ["STORAGE_CONTAINER"], key)
    blocks, _ = blob_client.get_block_list()
    assert [block.size for block in blocks] == [4 * 1024 * 1024, 1024 * 1024]


@pytest.mark.parametrize("size", [1024, 5 * 1024 * 1024])  # one request, blocks
def test_upload_reads_a_file_object_from_its_current_position(
    storage: Storage, size: int
) -> None:
    """As if a route read the start of the file to check that it is a video."""
    data = os.urandom(size)
    key = new_key()
    with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as file:
        file.write(b"HEADER" + data)
        file.seek(0)
        file.read(6)
        storage.upload(key, file, "video/mp4")

    response = httpx.get(storage.read_url(key))

    assert response.status_code == 200
    assert response.content == data


def test_upload_replaces_a_file_with_the_same_key(storage: Storage) -> None:
    key = new_key()
    storage.upload(key, b"first version", "video/mp4")

    storage.upload(key, VIDEO, "video/mp4")

    assert httpx.get(storage.read_url(key)).content == VIDEO


def test_file_cannot_be_read_without_a_link(storage: Storage) -> None:
    key = new_key()
    storage.upload(key, VIDEO, "video/mp4")

    response = httpx.get(without_signature(storage.read_url(key)))

    assert response.status_code == 403
    assert error_code(response) == "AuthorizationFailure"


def test_read_link_cannot_write_or_delete(storage: Storage) -> None:
    key = new_key()
    storage.upload(key, VIDEO, "video/mp4")
    link = storage.read_url(key)

    put = httpx.put(link, content=b"replaced", headers={"x-ms-blob-type": "BlockBlob"})
    delete = httpx.delete(link)

    assert put.status_code == 403
    assert error_code(put) == "AuthorizationPermissionMismatch"
    assert delete.status_code == 403
    assert error_code(delete) == "AuthorizationPermissionMismatch"
    assert httpx.get(link).content == VIDEO


def test_read_link_works_for_its_own_file_only(storage: Storage) -> None:
    key, other_key = new_key(), new_key()
    storage.upload(key, VIDEO, "video/mp4")
    storage.upload(other_key, b"someone else's video", "video/mp4")
    signature = urlsplit(storage.read_url(key)).query
    other_link = without_signature(storage.read_url(other_key))

    response = httpx.get(f"{other_link}?{signature}")

    assert response.status_code == 403
    assert error_code(response) == "AuthorizationFailure"


def test_expired_read_link_is_denied(storage: Storage) -> None:
    key = new_key()
    storage.upload(key, VIDEO, "video/mp4")
    link = storage.read_url(key, expires_in=timedelta(seconds=3))
    assert httpx.get(link).status_code == 200

    time.sleep(4)
    response = httpx.get(link)

    assert response.status_code == 403
    assert error_code(response) == "AuthorizationFailure"


def test_delete_removes_the_file_and_can_repeat(storage: Storage) -> None:
    key = new_key()
    storage.upload(key, VIDEO, "video/mp4")
    link = storage.read_url(key)

    storage.delete(key)

    response = httpx.get(link)
    assert response.status_code == 404
    assert error_code(response) == "BlobNotFound"
    storage.delete(key)  # already gone: no error
    storage.delete(new_key())  # never existed: no error


def test_container_is_private(
    storage: Storage, blob_service: BlobServiceClient
) -> None:
    container = blob_service.get_container_client(os.environ["STORAGE_CONTAINER"])

    assert container.get_container_properties().public_access is None
    storage.create_container_if_missing()  # already there: no error


def test_refuses_a_public_container(blob_service: BlobServiceClient) -> None:
    name = f"test-public-{uuid.uuid4().hex[:12]}"
    blob_service.create_container(name, public_access="blob")
    try:
        storage = Storage(os.environ["STORAGE_CONNECTION_STRING"], name)
        with pytest.raises(RuntimeError, match="allows public access"):
            storage.create_container_if_missing()
    finally:
        blob_service.delete_container(name)


def test_read_link_is_read_only_https_and_short_lived() -> None:
    """Signing a link makes no network call, so this needs no real Azure account."""
    link = azure_style_storage().read_url("sessions/1.mp4")

    url = urlsplit(link)
    query = {name: values[0] for name, values in parse_qs(url.query).items()}
    assert url.scheme == "https"
    assert url.path == "/videos/sessions/1.mp4"
    assert query["sp"] == "r"  # read only
    assert query["sr"] == "b"  # this one blob
    assert query["spr"] == "https"
    expiry = datetime.fromisoformat(query["se"])
    lifetime = expiry - datetime.now(UTC)
    assert timedelta(minutes=14) < lifetime <= timedelta(minutes=15)
    start = datetime.fromisoformat(query["st"])
    assert start <= datetime.now(UTC) - timedelta(minutes=4)  # 5 minutes early


@pytest.mark.parametrize(
    "expires_in", [timedelta(minutes=16), timedelta(0), timedelta(seconds=-1)]
)
def test_read_link_lifetime_is_capped_at_15_minutes(expires_in: timedelta) -> None:
    with pytest.raises(ValueError, match="at most 15 minutes"):
        azure_style_storage().read_url("sessions/1.mp4", expires_in=expires_in)


@pytest.mark.parametrize(
    "key",
    [
        "",
        "sessions/../1.mp4",
        "sessions/./1.mp4",
        "sessions//1.mp4",
        "/sessions/1.mp4",
        "sessions\\1.mp4",
        "sessions/pat@example.com.mp4",
    ],
)
def test_bad_keys_are_refused(key: str) -> None:
    """Keys are checked before any request, so this needs no storage."""
    storage = azure_style_storage()
    with pytest.raises(ValueError, match="storage key"):
        storage.upload(key, VIDEO, "video/mp4")
    with pytest.raises(ValueError, match="storage key"):
        storage.read_url(key)
    with pytest.raises(ValueError, match="storage key"):
        storage.delete(key)


def test_link_and_contents_are_not_logged(
    storage: Storage, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    contents = f"video {uuid.uuid4()}".encode()
    key = new_key()

    storage.upload(key, contents, "video/mp4")
    link = storage.read_url(key)
    storage.delete(key)

    sas = urlsplit(link).query
    assert "Request URL" in caplog.text  # the SDK logs its requests at this level...
    assert sas not in caplog.text  # ...but not read links
    assert parse_qs(sas)["sig"][0] not in caplog.text
    assert contents.decode() not in caplog.text  # ...or file contents


def test_storage_needs_a_connection_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(blob, "STORAGE_CONNECTION_STRING", "")

    with pytest.raises(RuntimeError, match="STORAGE_CONNECTION_STRING is not set"):
        blob.get_storage.__wrapped__()  # skip the cache
