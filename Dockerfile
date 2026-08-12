# Production image for Fly.io: React UI + FastAPI + local Redis (sessions).
FROM node:22-alpine AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt-get update \
  && apt-get install -y --no-install-recommends nginx redis-server wget \
  && rm -rf /var/lib/apt/lists/* \
  && rm -f /etc/nginx/sites-enabled/default

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/app ./app
COPY backend/templates ./templates
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/start.sh /start.sh
COPY --from=frontend /web/dist /usr/share/nginx/html

RUN chmod +x /start.sh

ENV PATH="/app/.venv/bin:$PATH"
ENV REQUIREMENTS_PATH=/app/templates/requirements.md
ENV DATA_DIR=/data
ENV DATABASE_PATH=/data/app.db
ENV REDIS_URL=redis://127.0.0.1:6379/0

EXPOSE 8080
CMD ["/start.sh"]
