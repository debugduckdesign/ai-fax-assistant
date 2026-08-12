import hmac
import json
import re
from pathlib import Path

from elevenlabs import ElevenLabs
from elevenlabs.errors import BadRequestError
from fastapi import Depends, Header, HTTPException, Request

from app.config import Settings, get_settings
from app.models.schemas import UserPublic, UserRole
from app.services import sessions, users

CASE_ID_RE = re.compile(r"^[a-f0-9]{12}$")


def validate_case_id(case_id: str) -> str:
    if not CASE_ID_RE.fullmatch(case_id):
        raise HTTPException(status_code=404, detail="Case not found")
    return case_id


def sniff_media_type(data: bytes) -> str | None:
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def safe_filename(filename: str) -> str:
    name = Path(filename or "scan.bin").name
    name = (
        name.replace("\x00", "")
        .replace("\r", "")
        .replace("\n", "")
        .replace('"', "")
        .replace("\\", "")
    )
    if not name or name in {".", ".."}:
        return "scan.bin"
    return name[:180]


def _constant_time_eq(provided: str, expected: str) -> bool:
    try:
        return hmac.compare_digest(provided, expected)
    except (TypeError, ValueError):
        return False


def _api_key_matches(
    x_api_key: str | None, authorization: str | None, settings: Settings
) -> bool:
    expected = settings.api_key
    if not expected:
        return False
    provided = x_api_key or ""
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if not provided:
        return False
    return _constant_time_eq(provided, expected)


async def require_user(
    request: Request,
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> UserPublic:
    settings = get_settings()

    if _api_key_matches(x_api_key, authorization, settings):
        return UserPublic(
            id="api-key",
            username="api-key",
            role=UserRole.ADMIN,
            is_active=True,
            created_at="",
        )

    sid = request.cookies.get(settings.session_cookie_name)
    if not sid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = sessions.get_session(sid, settings=settings)
    if not payload or not payload.get("user_id"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = users.get_user_by_id(str(payload["user_id"]), settings=settings)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def require_admin(user: UserPublic = Depends(require_user)) -> UserPublic:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def verify_elevenlabs_webhook(
    raw_body: bytes, signature: str | None, settings: Settings
) -> dict:
    secret = settings.elevenlabs_webhook_secret
    if not secret:
        if not settings.allow_insecure_webhooks:
            raise HTTPException(
                status_code=503,
                detail="Webhook HMAC secret is not configured",
            )
        try:
            return json.loads(raw_body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    if not signature:
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    client = ElevenLabs(api_key=settings.elevenlabs_api_key or "unused")
    try:
        return client.webhooks.construct_event(
            rawBody=raw_body.decode("utf-8"),
            sig_header=signature,
            secret=secret,
        )
    except BadRequestError as exc:
        raise HTTPException(
            status_code=401, detail="Invalid webhook signature"
        ) from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook body") from exc
