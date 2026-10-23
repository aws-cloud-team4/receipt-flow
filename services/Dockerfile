# One image recipe for every Python service:
#   docker build --build-arg SERVICE=api-service -t api-service services/
# The container command comes from the Kubernetes manifest (see deploy/k8s).
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /bin/uv

# opencv-python-headless still needs glib at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH=/app/.venv/bin:$PATH

ARG SERVICE
COPY pyproject.toml uv.lock ./
COPY common ./common
COPY api-service ./api-service
COPY chat-service ./chat-service
COPY preprocess-service ./preprocess-service
COPY ocr-worker ./ocr-worker
RUN test -n "$SERVICE" && uv sync --frozen --no-dev --package "$SERVICE"

USER app
EXPOSE 8000
