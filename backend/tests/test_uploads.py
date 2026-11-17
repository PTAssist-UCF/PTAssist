"""Upload checks without a database or storage: the size limit while an upload
arrives, the file's first bytes, and media-inspection errors and unknown durations."""

import asyncio
import io
import subprocess
import uuid

import httpx
import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app import uploads
from app.main import app
from app.schemas.analysis_contract import ERROR_MESSAGES

# The web app's origin, which conftest.py allows (CLERK_AUTHORIZED_PARTIES).
WEB_APP_ORIGIN = "http://localhost:5173"

# How each supported container starts: an MP4 "ftyp" box (size, type, brand), a
# QuickTime one, and the EBML magic number of WebM.
MP4_START = b"\x00\x00\x00\x18ftypisom"
MOV_START = b"\x00\x00\x00\x14ftypqt  "
WEBM_START = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81"


def fake_upload(contents=MP4_START + b"synthetic file", filename="exercise.mp4"):
    return UploadFile(
        file=io.BytesIO(contents),
        filename=filename,
        headers=Headers({"content-type": "video/mp4"}),
    )


@pytest.fixture
def probe(monkeypatch):
    """Stands in for ffprobe, and records each file it was asked to inspect. Answers
    with no metadata, so a file that reaches it ends 422 video_unreadable."""
    calls = []

    def fake_probe(path):
        calls.append(path)
        return {}

    monkeypatch.setattr(uploads, "_probe", fake_probe)
    return calls


@pytest.mark.parametrize(
    "contents",
    [
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,  # a photo
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00",  # a JPEG photo
        b"%PDF-1.7\n%synthetic document",  # a document
        b"<!DOCTYPE html><script>alert(1)</script>",  # a web page
        b"PK\x03\x04" + b"\x00" * 32,  # a zip archive
        b"not video",
        b"abc",  # shorter than any video's first bytes
    ],
)
@pytest.mark.parametrize("filename", ["exercise.mp4", "exercise.mov", "exercise.webm"])
def test_file_that_is_not_a_video_is_refused_before_inspection(
    probe, contents, filename
):
    """A renamed photo or document is refused by its first bytes: it is never copied
    to disk or given to ffprobe."""
    file = fake_upload(contents, filename)
    with pytest.raises(HTTPException) as error:
        uploads.validate_video(file)
    assert error.value.status_code == 415
    assert error.value.detail == uploads.WRONG_TYPE
    assert probe == []
    assert file.file.tell() == 0


@pytest.mark.parametrize(
    "contents,filename",
    [
        (WEBM_START, "exercise.mp4"),
        (WEBM_START, "exercise.mov"),
        (MP4_START, "exercise.webm"),
        (MOV_START, "exercise.webm"),
    ],
)
def test_first_bytes_of_another_format_than_the_name_are_refused(
    probe, contents, filename
):
    with pytest.raises(HTTPException) as error:
        uploads.validate_video(fake_upload(contents + b"synthetic file", filename))
    assert error.value.status_code == 415
    assert error.value.detail == uploads.WRONG_EXTENSION
    assert probe == []


@pytest.mark.parametrize(
    "first_box", sorted(uploads.MOV_FIRST_BOXES), ids=lambda box: box.decode()
)
@pytest.mark.parametrize("filename", ["exercise.mp4", "exercise.mov"])
def test_mp4_and_quicktime_starts_go_on_to_inspection(probe, first_box, filename):
    """Phones and browsers start with "ftyp"; older QuickTime files may start with
    another box. ffprobe then decides (here it finds nothing: 422)."""
    contents = b"\x00\x00\x00\x08" + first_box + b"synthetic file"
    with pytest.raises(HTTPException) as error:
        uploads.validate_video(fake_upload(contents, filename))
    assert error.value.status_code == 422
    assert len(probe) == 1


def test_webm_start_goes_on_to_inspection(probe):
    with pytest.raises(HTTPException) as error:
        uploads.validate_video(fake_upload(WEBM_START, "exercise.webm"))
    assert error.value.status_code == 422
    assert len(probe) == 1


def test_size_message_gives_the_limit_in_mb(monkeypatch):
    """The web app shows this message, and its own check says the same."""
    monkeypatch.setattr(uploads, "MAX_VIDEO_UPLOAD_BYTES", 500 * 1024**2)
    assert uploads.too_large_message() == (
        "Video exceeds the 500 MB limit. "
        "Please record a shorter or lower-resolution video."
    )


def post_upload(**request) -> httpx.Response:
    """POST /sessions to the app, which reads the body one chunk at a time.

    TestClient reads a whole request body before the app runs. httpx's ASGITransport
    hands over each chunk only when the app asks for it, so a test can see how much of
    an upload the API read. No sign-in is needed: the limit applies before it.
    """

    async def post() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post("/sessions", **request)

    return asyncio.run(post())


def test_upload_without_a_length_is_cut_off_at_the_limit(monkeypatch):
    """A chunked body has no Content-Length, so the API counts what arrives and stops
    reading once it passes the limit, instead of spooling all of it to disk."""
    monkeypatch.setattr(uploads, "MAX_VIDEO_UPLOAD_BYTES", 4096)
    monkeypatch.setattr(uploads, "FORM_OVERHEAD_BYTES", 1024)
    boundary = "synthetic-boundary"
    form_start = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="plan_exercise_id"\r\n\r\n'
        f"{uuid.uuid4()}\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="video"; filename="exercise.mp4"\r\n'
        "Content-Type: video/mp4\r\n\r\n"
    ).encode()
    chunks_read = 0

    async def endless_video():
        nonlocal chunks_read
        yield form_start + MP4_START
        for _ in range(100_000):  # 100 MiB, if the API read it all
            chunks_read += 1
            yield b"\x00" * 1024

    response = post_upload(
        content=endless_video(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": uploads.too_large_message()}
    # The limit is 5 KiB: the form's start and 4 chunks fit in it, the 5th crossed it,
    # and the API read nothing after that.
    assert chunks_read == 5


def test_upload_with_a_larger_length_is_refused_before_it_is_read(monkeypatch):
    """A Content-Length over the limit is refused at once, and the web app can read
    the answer (CORS)."""
    monkeypatch.setattr(uploads, "MAX_VIDEO_UPLOAD_BYTES", 4096)
    monkeypatch.setattr(uploads, "FORM_OVERHEAD_BYTES", 1024)
    body_read = []

    async def body():
        body_read.append(True)
        yield b"synthetic body"

    response = post_upload(
        content=body(),
        headers={
            "Content-Type": "multipart/form-data; boundary=synthetic-boundary",
            "Content-Length": str(4096 + 1024 + 1),
            "Origin": WEB_APP_ORIGIN,
        },
    )
    assert response.status_code == 413
    assert response.json() == {"detail": uploads.too_large_message()}
    assert response.headers["access-control-allow-origin"] == WEB_APP_ORIGIN
    assert body_read == []


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"streams": []},
        {"streams": [{"codec_type": "audio"}]},
        {"streams": [{"codec_type": "video", "disposition": {"attached_pic": 1}}]},
        {
            "streams": [{"codec_type": "video"}],
            "format": {"format_name": "mov", "duration": "nan"},
        },
        {
            "streams": [{"codec_type": "video"}],
            "format": {"format_name": "mov", "duration": "inf"},
        },
        {
            "streams": [{"codec_type": "video"}],
            "format": {"format_name": "mov", "duration": "N/A"},
        },
        {
            "streams": [{"codec_type": "video"}],
            "format": {"format_name": "mov", "duration": "0"},
        },
    ],
)
def test_unusable_metadata_is_rejected_and_file_is_rewound(monkeypatch, metadata):
    monkeypatch.setattr(uploads, "_probe", lambda path: metadata)
    file = fake_upload()
    with pytest.raises(HTTPException) as error:
        uploads.validate_video(file)
    assert error.value.status_code == 422
    assert file.file.tell() == 0


@pytest.mark.parametrize(
    "failure,status",
    [
        (FileNotFoundError(), 503),
        # Too slow on our side: not the video's fault, so not "record it again".
        (subprocess.TimeoutExpired("ffprobe", 15), 503),
        # ffprobe could not read the file: the video is unreadable.
        (subprocess.CalledProcessError(1, "ffprobe", stderr=b"private metadata"), 422),
    ],
)
def test_probe_failures_are_safe(monkeypatch, failure, status):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(uploads.subprocess, "run", fail)
    with pytest.raises(HTTPException) as error:
        uploads.validate_video(fake_upload())
    assert error.value.status_code == status
    assert "private metadata" not in str(error.value.detail)
    if status == 503:
        assert error.value.detail != ERROR_MESSAGES["video_unreadable"]
