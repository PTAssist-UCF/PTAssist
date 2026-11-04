"""App settings, read from environment variables (see /.env.example)."""

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
# by the shared analysis contract, independent of this byte limit.
MAX_VIDEO_UPLOAD_BYTES = int(os.environ.get("MAX_VIDEO_UPLOAD_BYTES", 500 * 1024**2))
if MAX_VIDEO_UPLOAD_BYTES <= 0:
    raise ValueError("MAX_VIDEO_UPLOAD_BYTES must be positive")
