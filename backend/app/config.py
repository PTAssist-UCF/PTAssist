"""App settings, read from environment variables (see /.env.example)."""

import math
import os

DATABASE_URL = os.environ["DATABASE_URL"]

# Clerk settings are optional here so Alembic can run without them. Without
# CLERK_SECRET_KEY, every route that needs sign-in fails with 500 and a message that
# says so (app/auth/clerk.py), and the API logs a warning when it starts (app/main.py).
CLERK_SECRET_KEY = os.environ.get("CLERK_SECRET_KEY", "")
# Web app origins allowed to send tokens (the token's "azp" claim), comma-separated.
# Empty means the origin is not checked.
CLERK_AUTHORIZED_PARTIES = [
    origin.strip()
    for origin in os.environ.get("CLERK_AUTHORIZED_PARTIES", "").split(",")
    if origin.strip()
]

# Storage settings are optional here too, so Alembic and the API start without them.
# Without STORAGE_CONNECTION_STRING, anything that uses storage fails with 500.
# Locally "UseDevelopmentStorage=true" (Azurite on 127.0.0.1:10000). In Azure, the
# storage account's connection string, which holds its key.
STORAGE_CONNECTION_STRING = os.environ.get("STORAGE_CONNECTION_STRING", "")
# The private blob container for videos. The API creates it if it is missing.
STORAGE_CONTAINER = os.environ.get("STORAGE_CONTAINER") or "videos"

# 500 MiB fits two-minute 1080p phone recordings. While an upload is checked, the API
# holds it on temporary disk twice (the received file and an inspection copy), and
# Azure Container Apps gives a container only a few GiB of it. Duration is still capped
# by the shared analysis contract, independent of this byte limit. The API stops
# reading an upload that passes this limit (app/uploads.py). The web app has its own
# copy in frontend/src/utils/videoValidation.ts: change both together.
MAX_VIDEO_UPLOAD_BYTES = int(os.environ.get("MAX_VIDEO_UPLOAD_BYTES", 500 * 1024**2))
if MAX_VIDEO_UPLOAD_BYTES <= 0:
    raise ValueError("MAX_VIDEO_UPLOAD_BYTES must be positive")

# The AI service, which only the API calls (POST /analyze). Locally
# http://localhost:8001, in Docker Compose http://ai:8001, in Azure the AI container
# app's internal URL.
AI_SERVICE_URL = os.environ.get("AI_SERVICE_URL") or "http://localhost:8001"
# Seconds the background analysis waits for a connection to the AI service, before it
# waits AI_SERVICE_TIMEOUT_SECONDS for the answer. A fixed value, not an environment
# variable. In Azure the connection goes to the Container Apps ingress, which accepts
# it at once, even while the AI container starts from zero. Only the answer can take
# long.
AI_SERVICE_CONNECT_TIMEOUT_SECONDS = 10
# How long the background analysis waits for POST /analyze to answer before it saves
# the session as failed with analysis_timed_out. A 2-minute clip may take 3 minutes to
# analyze from a cold start, and Azure Container Apps ends any request after 240
# seconds, so keep it between 180 and 240 in Azure (docs/analysis-result.md, Clip
# limits and timing).
AI_SERVICE_TIMEOUT_SECONDS = float(os.environ.get("AI_SERVICE_TIMEOUT_SECONDS", 230))
if not (math.isfinite(AI_SERVICE_TIMEOUT_SECONDS) and AI_SERVICE_TIMEOUT_SECONDS > 0):
    raise ValueError("AI_SERVICE_TIMEOUT_SECONDS must be a positive number")

# Sessions processing for longer than this, counted from the upload, are saved as
# failed with analysis_timed_out when the API starts and when their status is read
# (app/jobs/stuck_sessions.py). It must be longer than the background analysis can
# wait for the AI service (to connect, then for the answer), so the cleanup never
# fails a session the analysis is still waiting on. Empty or unset: 30 seconds more
# than that wait, for the analysis's other steps, which is 270 with the default
# timeout. The web app's polling timeout (POLL_TIMEOUT_MS in
# frontend/src/hooks/useSessionStatus.ts, 300 seconds) must be at least this long
# (docs/analysis-result.md, Clip limits and timing).
_LONGEST_AI_WAIT_SECONDS = (
    AI_SERVICE_CONNECT_TIMEOUT_SECONDS + AI_SERVICE_TIMEOUT_SECONDS
)
STUCK_SESSION_CUTOFF_SECONDS = float(
    os.environ.get("STUCK_SESSION_CUTOFF_SECONDS") or _LONGEST_AI_WAIT_SECONDS + 30
)
if not (
    math.isfinite(STUCK_SESSION_CUTOFF_SECONDS)
    and STUCK_SESSION_CUTOFF_SECONDS > _LONGEST_AI_WAIT_SECONDS
):
    raise ValueError(
        "STUCK_SESSION_CUTOFF_SECONDS must be longer than AI_SERVICE_TIMEOUT_SECONDS "
        f"plus {AI_SERVICE_CONNECT_TIMEOUT_SECONDS} seconds to connect"
    )

# How the API writes its log lines (app/logs.py): "json", one JSON object per line
# with the session id (backend/README.md, Logs), or "text", easier to read in a
# terminal. Empty or unset: json. The API refuses to start with any other value.
LOG_FORMAT = os.environ.get("LOG_FORMAT") or "json"
