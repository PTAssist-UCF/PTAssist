"""Media-inspection error paths and unknown durations are rejected safely."""

import io
import subprocess

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app import uploads


def fake_upload():
    return UploadFile(
        file=io.BytesIO(b"synthetic file"),
        filename="exercise.mp4",
        headers=Headers({"content-type": "video/mp4"}),
    )


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
        (subprocess.TimeoutExpired("ffprobe", 15), 422),
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
