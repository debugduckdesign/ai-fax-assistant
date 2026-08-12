import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import auth, calls, cases, requirements, users, webhooks
from app.config import get_settings
from app.db import init_db
from app.services import sessions
from app.services.requirements import ensure_requirements_file
from app.services.users import seed_admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        return response


def _warn_insecure_defaults() -> None:
    settings = get_settings()
    if settings.admin_password in {"admin", "password", "changeme"}:
        logger.warning(
            "ADMIN_PASSWORD is a well-known default; change it before any shared deploy"
        )
    if settings.session_secret in {
        "dev-session-secret-change-me",
        "change-me-to-a-long-random-string",
    }:
        logger.warning(
            "SESSION_SECRET is still the example default; rotate it for shared envs"
        )
    if (
        settings.webhook_base_url.startswith("https://")
        and not settings.session_cookie_secure
    ):
        logger.warning("WEBHOOK_BASE_URL is HTTPS but SESSION_COOKIE_SECURE is false")
    if settings.allow_insecure_webhooks:
        logger.warning(
            "ALLOW_INSECURE_WEBHOOKS is enabled — webhook authenticity is not verified"
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    init_db(settings)
    seed_admin(settings)
    ensure_requirements_file(settings)
    _warn_insecure_defaults()
    if not sessions.ping(settings):
        logger.warning(
            "Redis not reachable at %s — login sessions will fail until it is up",
            settings.redis_url,
        )
    yield
    sessions.reset_redis()


settings = get_settings()

app = FastAPI(title="AI Fax Assistant", version="0.2.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(calls.router)
app.include_router(cases.router)
app.include_router(requirements.router)
# HMAC-verified (or explicitly insecure when ALLOW_INSECURE_WEBHOOKS=true).
app.include_router(webhooks.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
