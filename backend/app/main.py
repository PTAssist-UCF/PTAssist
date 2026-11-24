"""Entry point: creates the FastAPI app and plugs in every router."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.config import CLERK_AUTHORIZED_PARTIES, CLERK_SECRET_KEY, LOG_FORMAT
from app.jobs.stuck_sessions import fail_stuck_sessions_at_startup
from app.logs import configure_logging
from app.routes import (
    exercises,
    health,
    me,
    plans,
    results,
    sessions,
    therapist_patients,
)
from app.uploads import UploadSizeLimitMiddleware

logger = logging.getLogger(__name__)

# Every log line goes to stdout, uvicorn's included: JSON (or text, see LOG_FORMAT),
# with the session id where there is one, and no personal data (app/logs.py,
# backend/README.md, Logs). First, so the warning below is written that way too.
configure_logging("api", LOG_FORMAT)

# The API starts without the Clerk secret key (see app/config.py), so say so in its log
# right away, not only when someone tries to sign in.
if not CLERK_SECRET_KEY:
    logger.warning(
        "CLERK_SECRET_KEY is not set: the API runs, but sign-in won't work. "
        "See /.env.example."
    )


def operation_id_from_function_name(route: APIRoute) -> str:
    """Name each operation in the API description after its route function.

    The frontend's generated hooks are named after these ids, so `def get_me` becomes
    `useGetMe()` (FastAPI's default would be `useGetMeMeGet()`). Route function names
    must therefore be unique across the API; a test checks this.
    """
    return route.name


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Runs once when the API starts, before it takes requests."""
    # An API that stopped during an analysis (a deploy, scaling in, a crash) left its
    # session processing, with nothing running for it any more. Fail the ones stuck
    # longer than STUCK_SESSION_CUTOFF_SECONDS (app/jobs/stuck_sessions.py). In a
    # worker thread, because it uses the database; it takes milliseconds.
    await run_in_threadpool(fail_stuck_sessions_at_startup)
    yield


app = FastAPI(
    title="PTAssist API",
    generate_unique_id_function=operation_id_from_function_name,
    lifespan=lifespan,
)

# Stops reading an upload once it passes the size limit (app/uploads.py). Added before
# CORS, so CORS wraps it, and the web app can read the 413 it answers.
app.add_middleware(UploadSizeLimitMiddleware)

# Browser access (CORS). The web app runs on a different origin than the API
# (http://localhost:5173 locally, the Static Web Apps URL in Azure), so a browser only
# lets it read the API's answers if the API names that origin as allowed. The allowed
# origins are the ones in CLERK_AUTHORIZED_PARTIES, the same list sign-in already
# checks. The token travels in the Authorization header, not in cookies, so
# credentials (cookies) are not allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CLERK_AUTHORIZED_PARTIES,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(exercises.router)
app.include_router(health.router)
app.include_router(me.router)
app.include_router(plans.router)
app.include_router(results.router)
app.include_router(sessions.router)
app.include_router(therapist_patients.router)
