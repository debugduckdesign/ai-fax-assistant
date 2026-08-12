# Backend

FastAPI service for fax intake, extraction, calling, auth, and admin APIs.

## Run

Prefer root `docker compose up --build`, or locally:

```bash
# Redis required for sessions
docker compose up -d redis

uv sync
uv run uvicorn app.main:app --reload --port 8000
```

## Format / lint

```bash
uv run black app
uv run ruff check app
```
