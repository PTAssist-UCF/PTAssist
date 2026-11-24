"""Structured logs (SCRUM-83): one JSON object per line, with the session id, and
nothing personal.

This file is shared: backend/app/logs.py is the original, and ai/app/logs.py is an
exact copy. Edit only the backend file, then copy it over from the repo root:
`cp backend/app/logs.py ai/app/logs.py`. A test in each service fails if they differ.

Each service's app/main.py calls configure_logging when it is imported. After that:

- Log with logging.getLogger(__name__), as before. Our own lines (app.*) show from
  INFO, other libraries' from WARNING, because some of them (the Azure SDK, httpx) log
  request URLs at INFO.
- Wrap the work for one session in `with session_context(session_id):`. Every line
  logged inside, by our code or by a library it calls, then carries the session id,
  so one session can be followed through the logs (backend/README.md, Logs).
- Give a line more facts with `extra=`, such as `extra={"error_code": "no_person"}`.
  Only the fields in FIELDS are written: a field that is not listed is dropped. List
  a new one only if it can never hold personal data, a token, or a link.

What keeps personal data out of the logs:

- The rule: messages carry ids, codes, and outcomes, never names, emails, tokens,
  video links, file names, or results (results are health data).
- Only the fields in FIELDS are written, never a record's other attributes.
- uvicorn's access lines leave out the caller's address and the query string.
- A safety net, in case the rule is broken somewhere: redact() masks anything that
  looks like an email address, a token, a link's query string or fragment (a read
  link keeps its signature in the query string), or a password or key in a
  connection string. It runs on every message, field, and traceback.
"""

import json
import logging
import re
import sys
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, TextIO

LOG_FORMATS = ("json", "text")

# The facts a line may carry besides its message, in this order. Each is an id, a
# code, a number, or a fixed word: never personal data, a token, or a link.
FIELDS = (
    "session_id",
    "method",  # an access line's HTTP method
    "path",  # an access line's path, without the query string
    "status_code",  # an HTTP status
    "duration_seconds",
    "outcome",  # how an analysis ended: complete or failed
    "error_code",  # an analysis error code (docs/analysis-result.md, Failures)
    "error_type",  # an exception's class name, never its message
    "analyzer_version",
)

# configure_logging names its handler, so calling it again replaces the handler.
HANDLER_NAME = "ptassist"

_session_id: ContextVar[str | None] = ContextVar("session_id", default=None)


@contextmanager
def session_context(session_id: uuid.UUID | str) -> Iterator[None]:
    """Add session_id to every line logged inside the `with` block.

    The id is a context variable, so it follows the code into every function it
    calls, and into an asyncio task or a FastAPI worker thread (run_in_threadpool)
    started inside the block. Other requests and threads don't see it, and neither
    does a plain thread (threading.Thread) started inside it.
    """
    token = _session_id.set(str(session_id))
    try:
        yield
    finally:
        _session_id.reset(token)


def _pattern(regex: str) -> re.Pattern[str]:
    return re.compile(regex, re.IGNORECASE)


def _without_query(link: re.Match[str]) -> str:
    """A link with its query string and fragment masked, where tokens travel. A read
    link (SAS URL) keeps its signature in the query string."""
    cut = re.search(r"[?#]", link.group())
    return link.group() if cut is None else link.group()[: cut.end()] + "[redacted]"


# What redact() masks, in this order. Each keeps what helps to debug (a link's path,
# a setting's name) and masks the secret part. Repeats that could start anywhere are
# capped ({1,64} and the like), so a long line can't make a pattern slow.
_REDACTIONS: list[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]] = [
    # Links, and a signature outside a link.
    (_pattern(r"\bhttps?://[^\s\"'<>]+"), _without_query),
    (_pattern(r"\b(sig=)[^&\s\"'<>]+"), r"\1[redacted]"),
    # The password in a URL, such as a database URL (scheme://user:password@host).
    (
        _pattern(r"(\b[a-z][a-z0-9+.-]{0,30}://[^\s:/@\"']+:)[^\s@/\"']+@"),
        r"\1[redacted]@",
    ),
    # A key or password in a connection string.
    (
        _pattern(r"\b(AccountKey|SharedAccessSignature|Password|Pwd)=[^;\s\"']+"),
        r"\1=[redacted]",
    ),
    # Tokens: a bearer token, a JWT (Clerk session tokens are JWTs), a Clerk key.
    (_pattern(r"\b(Bearer)\s+[\w.~+/=-]{20,}"), r"\1 [redacted]"),
    (re.compile(r"\beyJ[\w-]{0,1024}\.[\w-]{1,16384}\.[\w-]{0,1024}"), "[redacted]"),
    (re.compile(r"\bsk_(?:test|live)_\w+"), "[redacted]"),
    # Email addresses.
    (
        _pattern(r"[\w.%+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63})*\.[a-z]{2,63}"),
        "[redacted email]",
    ),
]


def redact(text: str) -> str:
    """Mask emails, tokens, link query strings, and secrets in connection strings."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


# A session id in a path, such as GET /sessions/{session_id}/result.
_SESSION_PATH = _pattern(
    r"/sessions/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:/|$)"
)


def _access_line(record: logging.LogRecord) -> tuple[str, dict[str, Any]] | None:
    """uvicorn's access line as a message and fields, or None for any other line.

    uvicorn logs the caller's address, the method, the path with its query string,
    the HTTP version, and the status. This keeps the method, the path without the
    query string, and the status. A path with a session id, such as the web app
    polling GET /sessions/{session_id}, also gets that id as session_id.
    """
    if record.name != "uvicorn.access" or not isinstance(record.args, tuple):
        return None
    if len(record.args) != 5:
        return None
    _address, method, path_and_query, _http_version, status_code = record.args
    if not (isinstance(path_and_query, str) and isinstance(status_code, int)):
        return None
    path = path_and_query.split("?", 1)[0]
    fields: dict[str, Any] = {
        "method": method,
        "path": path,
        "status_code": status_code,
    }
    if match := _SESSION_PATH.search(path):
        fields["session_id"] = match.group(1).lower()
    return f"{method} {path} {status_code}", fields


def _message_and_fields(record: logging.LogRecord) -> tuple[str, dict[str, Any]]:
    """The line's message and fields, redacted. A line without a session id of its
    own gets the one from session_context, if any."""
    access = _access_line(record)
    if access is not None:
        message, fields = access
    else:
        message = record.getMessage()
        fields = {
            name: getattr(record, name)
            for name in FIELDS
            if getattr(record, name, None) is not None
        }
    if "session_id" not in fields and (session_id := _session_id.get()) is not None:
        fields["session_id"] = session_id
    if "path" in fields:  # a query string can hold a token, from any logger
        fields["path"] = str(fields["path"]).split("?", 1)[0]
    ordered = {name: _clean(fields[name]) for name in FIELDS if name in fields}
    return redact(message), ordered


def _clean(value: Any) -> Any:
    """A field's value: a number as it is, anything else as redacted text (a UUID or
    an enum becomes its plain value)."""
    if isinstance(value, bool | int | float):
        return value
    return redact(str(value))


def _timestamp(record: logging.LogRecord) -> str:
    """When the line was logged, in UTC, such as 2026-11-23T18:04:05.123Z."""
    time = datetime.fromtimestamp(record.created, UTC)
    return time.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class JsonFormatter(logging.Formatter):
    """One JSON object per line: time, level, service, logger, message, the fields
    that are set, and the redacted traceback if there is one."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        message, fields = _message_and_fields(record)
        line: dict[str, Any] = {
            "time": _timestamp(record),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": message,
            **fields,
        }
        if record.exc_info:
            line["exception"] = redact(self.formatException(record.exc_info))
        if record.stack_info:
            line["stack"] = redact(self.formatStack(record.stack_info))
        return json.dumps(line)


class TextFormatter(logging.Formatter):
    """A readable line for a terminal: time, level, logger, message, the fields as
    name=value, and the redacted traceback on the lines below."""

    def format(self, record: logging.LogRecord) -> str:
        message, fields = _message_and_fields(record)
        line = f"{_timestamp(record)} {record.levelname:<7} {record.name}: {message}"
        line += "".join(f" {name}={value}" for name, value in fields.items())
        if record.exc_info:
            line += "\n" + redact(self.formatException(record.exc_info))
        if record.stack_info:
            line += "\n" + redact(self.formatStack(record.stack_info))
        return line


def _not_a_health_check(record: logging.LogRecord) -> bool:
    """False for the access line of a GET /health that worked: Docker Compose calls
    it every 5 seconds, which would bury every other line. A failed one is kept."""
    access = _access_line(record)
    if access is None:
        return True
    _message, fields = access
    return not (fields["path"] == "/health" and fields["status_code"] < 400)


def configure_logging(
    service: str, log_format: str = "json", stream: TextIO | None = None
) -> None:
    """Write every log line to stdout (or stream), as JSON or as text.

    service names the service in each JSON line, such as "api". Calling this again
    replaces its handler, so no line is written twice. Other handlers are kept.

    uvicorn sets up its own loggers before it imports the app. This sends their lines
    through this handler instead, so the server's own lines are JSON too, and its
    access lines leave out the caller's address. Their levels stay as uvicorn set
    them.
    """
    if log_format not in LOG_FORMATS:
        raise ValueError(
            f"LOG_FORMAT must be one of: {', '.join(LOG_FORMATS)} (got {log_format!r})"
        )
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(
        JsonFormatter(service) if log_format == "json" else TextFormatter()
    )
    handler.addFilter(_not_a_health_check)

    root = logging.getLogger()
    for old in [h for h in root.handlers if h.get_name() == HANDLER_NAME]:
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    logging.getLogger("app").setLevel(logging.INFO)

    # A logger without handlers is left alone: uvicorn is not running (tests), or its
    # access lines are turned off (uvicorn --no-access-log).
    for name in ("uvicorn", "uvicorn.access"):
        server_logger = logging.getLogger(name)
        if server_logger.handlers:
            server_logger.handlers.clear()
            server_logger.propagate = True
