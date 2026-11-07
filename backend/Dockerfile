# syntax=docker/dockerfile:1
# Two targets:
#   runtime (default, last stage): runtime deps only, non-root, no auto-reload.
#       docker build -t ops-copilot-api backend
#   dev: + test/lint tools, source bind-mounted and reloaded by docker-compose.yml.

# ---- base: Python + runtime dependencies (cached until requirements.txt changes) ----
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /uploads /models \
    && chown app:app /uploads /models
COPY requirements.txt ./
RUN pip install -r requirements.txt

# ---- dev: what `docker compose up` runs (code is bind-mounted over /app) ----
FROM base AS dev
COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---- runtime: production-shaped image ----
FROM base AS runtime
COPY --chown=app:app . .
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
# Migrations are idempotent; with several replicas, run them as a separate release step instead.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --proxy-headers"]
