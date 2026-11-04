# Builds the API image. The same image also runs migrations (alembic upgrade head).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# ffprobe inspects an upload's real container and duration before it is accepted.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

# Run as a non-root user.
RUN useradd --system --no-create-home app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
