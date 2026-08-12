from __future__ import annotations

import json
import secrets
from typing import Any

import redis

from app.config import Settings, get_settings

_redis: redis.Redis | None = None


def get_redis(settings: Settings | None = None) -> redis.Redis:
    global _redis
    settings = settings or get_settings()
    if _redis is None:
        _redis = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
        )
    return _redis


def reset_redis() -> None:
    global _redis
    if _redis is not None:
        try:
            _redis.close()
        except Exception:
            pass
    _redis = None


def _key(session_id: str) -> str:
    return f"session:{session_id}"


def create_session(payload: dict[str, Any], settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    client = get_redis(settings)
    session_id = secrets.token_urlsafe(32)
    client.setex(
        _key(session_id),
        settings.session_ttl_seconds,
        json.dumps(payload),
    )
    return session_id


def get_session(
    session_id: str, settings: Settings | None = None
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    client = get_redis(settings)
    raw = client.get(_key(session_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    client.expire(_key(session_id), settings.session_ttl_seconds)
    return data


def delete_session(session_id: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    get_redis(settings).delete(_key(session_id))


def ping(settings: Settings | None = None) -> bool:
    try:
        return bool(get_redis(settings).ping())
    except Exception:
        return False


def allow_login_attempt(client_key: str, settings: Settings | None = None) -> bool:
    """Return False when the client exceeded login attempts in the window."""
    settings = settings or get_settings()
    if settings.login_rate_limit <= 0:
        return True
    # Sanitize redis key material from untrusted client identifiers.
    safe = "".join(c if c.isalnum() or c in ".:_-" else "_" for c in client_key)[:200]
    key = f"ratelimit:login:{safe}"
    try:
        client = get_redis(settings)
        count = int(client.incr(key))
        if count == 1:
            client.expire(key, settings.login_rate_window_seconds)
        return count <= settings.login_rate_limit
    except Exception:
        # Fail open if Redis is briefly unavailable so operators can still recover.
        return True
