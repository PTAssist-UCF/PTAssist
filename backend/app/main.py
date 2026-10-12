"""Entry point: creates the FastAPI app and plugs in every router."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.config import CLERK_AUTHORIZED_PARTIES
from app.routes import health, me


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
