"""The API's only storage code: upload a file, make a temporary read link, delete it.

Built on the Azure Blob SDK. Locally it talks to Azurite (Microsoft's Azure Storage
emulator), in the cloud to our Azure storage account; only the connection string
differs. Files live in one private container and are read only through short-lived,
read-only links (SAS URLs).
"""

import os
import re
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import BinaryIO

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    LinearRetry,
    generate_blob_sas,
)

from app.config import STORAGE_CONNECTION_STRING, STORAGE_CONTAINER

# Read links last 15 minutes by default, and never longer (SCRUM-85).
MAX_LINK_LIFETIME = timedelta(minutes=15)
# Links start a little in the past, so storage whose clock runs behind ours still
# accepts a brand-new link.
_CLOCK_SKEW = timedelta(minutes=5)
# Files up to this size go up in one request, larger ones in blocks of this size. An
# upload then holds about this much in memory, not the SDK's default of 64 MB.
_CHUNK_SIZE = 4 * 1024 * 1024
# A key is "/"-separated parts made of letters, digits, ".", "_" and "-", such as
# sessions/<session id>.mp4. Other keys can break in confusing ways: the HTTP client
# rewrites "." and ".." parts after the request is signed, so storage rejects the
# signature, and a backslash gives read links that never work.
_KEY_PART = re.compile(r"[A-Za-z0-9._-]+")


class Storage:
    """Files in one private blob container. A key is a file's name in the container."""

    def __init__(self, connection_string: str, container: str) -> None:
        service = BlobServiceClient.from_connection_string(
            connection_string,
            max_single_put_size=_CHUNK_SIZE,
            max_block_size=_CHUNK_SIZE,
            # The SDK waits 15 seconds or more between retries by default. Retry 3 times
            # about a second apart instead, and wait at most 5 seconds to connect (the
            # default is 20). If storage refuses the connection, a request then fails
            # within seconds; if it does not answer, in about 25 seconds. Replies keep
            # the SDK's 60-second limit, which a slow 4 MB block upload can need.
            retry_policy=LinearRetry(backoff=1, random_jitter_range=1, retry_total=3),
            connection_timeout=5,
        )
        # Read links are signed with the account key: the SDK's built-in Azurite key for
        # UseDevelopmentStorage=true, or the AccountKey in Azure's connection string.
        self._account_key = getattr(service.credential, "account_key", None)
        if not self._account_key:
            raise RuntimeError(
                "The storage connection string has no account key to sign read links"
            )
        self._https = service.scheme == "https"
        self._container = service.get_container_client(container)

    def create_container_if_missing(self) -> None:
        """Create the container as private if it does not exist. Refuse a public one."""
        try:
            self._container.create_container()  # no public_access: private
        except ResourceExistsError:
            pass
        if self._container.get_container_properties().public_access is not None:
            raise RuntimeError(
                f"Storage container {self._container.container_name!r} "
                "allows public access. Make it private."
            )

    def upload(self, key: str, data: bytes | BinaryIO, content_type: str) -> None:
        """Store data under key, replacing any file with the same key.

        data is bytes or a binary file object, such as FastAPI's UploadFile.file. A file
        object is read from its current position, 4 MB at a time, not all at once.
        """
        _check_key(key)
        length = None
        if not isinstance(data, bytes) and data.seekable():
            # Size the file from its current position. Otherwise the SDK takes the size
            # of the whole file, so a file that was partly read (say, to check its
            # header) sends fewer bytes than it announces and fails with a 403.
            start = data.tell()
            length = data.seek(0, os.SEEK_END) - start
            data.seek(start)
        self._container.upload_blob(
            key,
            data,
            length=length,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    def read_url(self, key: str, expires_in: timedelta = MAX_LINK_LIFETIME) -> str:
        """A link that can only read this one file, and only for expires_in from now.

        Anyone holding the link can read the file until it expires, so treat it as a
        secret: never log it, and give it only to the service that needs it. It does
        not check that the file exists; a link to a missing file returns 404.
        """
        if not timedelta(0) < expires_in <= MAX_LINK_LIFETIME:
            raise ValueError("expires_in must be more than 0 and at most 15 minutes")
        _check_key(key)
        blob = self._container.get_blob_client(key)
        now = datetime.now(UTC)
        sas = generate_blob_sas(
            account_name=blob.account_name,
            container_name=blob.container_name,
            blob_name=blob.blob_name,
            account_key=self._account_key,
            permission=BlobSasPermissions(read=True),
            start=now - _CLOCK_SKEW,
            expiry=now + expires_in,
            # HTTPS only. Azurite serves plain HTTP, so links to it allow both.
            protocol="https" if self._https else None,
        )
        return f"{blob.url}?{sas}"

    def delete(self, key: str) -> None:
        """Delete the file. Deleting a file that is not there is not an error."""
        _check_key(key)
        try:
            self._container.delete_blob(key)
        except ResourceNotFoundError:
            pass


def _check_key(key: str) -> None:
    """Raise ValueError for a key that storage would mishandle (see _KEY_PART)."""
    # The message leaves the key out, in case a caller ever builds one from user data.
    parts = key.split("/")
    if not all(_KEY_PART.fullmatch(part) and part not in (".", "..") for part in parts):
        raise ValueError(
            'A storage key must be "/"-separated parts of letters, digits, ".", "_" '
            'and "-", without "." or ".." parts'
        )


@cache
def get_storage() -> Storage:
    """One storage client for all requests. A dependency, so tests can swap it."""
    if not STORAGE_CONNECTION_STRING:
        raise RuntimeError("STORAGE_CONNECTION_STRING is not set")
    storage = Storage(STORAGE_CONNECTION_STRING, STORAGE_CONTAINER)
    storage.create_container_if_missing()
    return storage
