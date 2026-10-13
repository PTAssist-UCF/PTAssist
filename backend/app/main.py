"""Entry point: creates the FastAPI app and plugs in every router."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.config import CLERK_AUTHORIZED_PARTIES, CLERK_SECRET_KEY
from app.routes import health, me

logger = logging.getLogger(__name__)

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


app = FastAPI(
    title="PTAssist API", generate_unique_id_function=operation_id_from_function_name
)

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

app.include_router(health.router)
app.include_router(me.router)
