# Builds the AI service image: Python, plus ffmpeg, OpenCV, and MediaPipe.
# Uses Debian 13 ("trixie") on purpose: the apt package names below belong to it.
FROM python:3.12-slim-trixie

ENV PYTHONUNBUFFERED=1
# Importing MediaPipe also loads matplotlib, which needs a folder it can write its
# cache to. The app user below has no home folder, so use /tmp.
ENV MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app

# Programs and system libraries that pip can't install:
# - ffmpeg: the program that reads and converts videos (rotation, frame rate, size).
# - libgl1, libglib2.0-0t64: libraries the OpenCV package needs to load at all
#   (without them, `import cv2` fails).
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg libgl1 libglib2.0-0t64 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as a non-root user.
RUN useradd --system --no-create-home app
USER app

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
