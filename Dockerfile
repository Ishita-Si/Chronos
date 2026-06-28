# CHRONOS — Unread Plant Memory Engine. Zero-dependency: a bare Python image.
FROM python:3.12-slim

WORKDIR /app
COPY . /app

# Bind to all interfaces for container/cloud hosting.
ENV CHRONOS_HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1

# Build the plant memory at image-build time so the first request is instant.
RUN python -m chronos.pipeline --reset

EXPOSE 8000
CMD ["python", "-m", "chronos.server"]
