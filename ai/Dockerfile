# Builds the AI service image: Python, plus ffmpeg, OpenCV, and MediaPipe.
# Uses Debian 13 ("trixie") on purpose: the apt package names below belong to it.
FROM python:3.12-slim-trixie

# Show print() and log output in `docker logs` right away, instead of buffering it.
ENV PYTHONUNBUFFERED=1
# Importing MediaPipe also loads matplotlib, which needs a folder it can write its
# cache to. The app user below has no home folder, so use /tmp.
ENV MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app

# Programs and system libraries that pip can't install:
# - ffmpeg: the program that reads and converts videos (rotation, frame rate, size).
# - libgl1, libglib2.0-0t64, libxcb1: OpenCV needs these to load at all. Without
#   them `import cv2` fails, and so does `import mediapipe`, which imports OpenCV.
# - libegl1, libgles2: MediaPipe's own code needs these to start, even on the CPU
#   with no graphics card. Without them, creating a pose model fails.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ffmpeg \
        libgl1 libglib2.0-0t64 libxcb1 \
        libegl1 libgles2 \
    && rm -rf /var/lib/apt/lists/*

# Install the Python packages before copying our code. Docker then reuses this slow
# step when only the code in app/ changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as a non-root user.
RUN useradd --system --no-create-home app
USER app

# Listen on 0.0.0.0 so other containers and your computer can reach the service
# (127.0.0.1 would only accept calls from inside this container).
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
