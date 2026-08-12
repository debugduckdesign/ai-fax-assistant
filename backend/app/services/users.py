from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime

import bcrypt

from app.config import Settings, get_settings
from app.db import get_connection
from app.models.schemas import UserPublic, UserRole

# bcrypt silently truncates beyond 72 bytes
MAX_PASSWORD_BYTES = 72


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def validate_password(password: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if len(password) < settings.min_password_length:
        raise ValueError(
            f"Password must be at least {settings.min_password_length} characters"
        )
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _row_to_user(row) -> UserPublic:
    return UserPublic(
        id=row["id"],
        username=row["username"],
        role=UserRole(row["role"]),
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
    )


def seed_admin(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    with get_connection(settings) as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (settings.admin_username,),
        ).fetchone()
        if existing:
            return
        conn.execute(
            """
            INSERT INTO users (
                id, username, password_hash, role, is_active, created_at
            )
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (
                uuid.uuid4().hex,
                settings.admin_username,
                hash_password(settings.admin_password),
                UserRole.ADMIN.value,
                _utcnow(),
            ),
        )


def get_user_by_id(user_id: str, settings: Settings | None = None) -> UserPublic | None:
    settings = settings or get_settings()
    with get_connection(settings) as conn:
        row = conn.execute(
            "SELECT id, username, role, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_username(
    username: str, settings: Settings | None = None
) -> tuple[UserPublic, str] | None:
    settings = settings or get_settings()
    with get_connection(settings) as conn:
        row = conn.execute(
            """
            SELECT id, username, password_hash, role, is_active, created_at
            FROM users WHERE username = ?
            """,
            (username,),
        ).fetchone()
    if not row:
        return None
    user = _row_to_user(row)
    return user, row["password_hash"]


def authenticate(
    username: str, password: str, settings: Settings | None = None
) -> UserPublic | None:
    found = get_user_by_username(username, settings=settings)
    if not found:
        return None
    user, password_hash = found
    if not user.is_active:
        return None
    if not verify_password(password, password_hash):
        return None
    return user


def list_users(settings: Settings | None = None) -> list[UserPublic]:
    settings = settings or get_settings()
    with get_connection(settings) as conn:
        rows = conn.execute("""
            SELECT id, username, role, is_active, created_at
            FROM users
            ORDER BY created_at ASC
            """).fetchall()
    return [_row_to_user(r) for r in rows]


def create_user(
    username: str,
    password: str,
    role: UserRole,
    settings: Settings | None = None,
) -> UserPublic:
    settings = settings or get_settings()
    username = username.strip()
    if not username:
        raise ValueError("Username is required")
    validate_password(password, settings=settings)
    user_id = uuid.uuid4().hex
    created_at = _utcnow()
    with get_connection(settings) as conn:
        try:
            conn.execute(
                """
                INSERT INTO users (
                    id, username, password_hash, role, is_active, created_at
                )
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (
                    user_id,
                    username,
                    hash_password(password),
                    role.value,
                    created_at,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Username already exists") from exc
    user = get_user_by_id(user_id, settings=settings)
    if user is None:
        raise RuntimeError("Failed to load created user")
    return user


def update_user(
    user_id: str,
    *,
    role: UserRole | None = None,
    is_active: bool | None = None,
    password: str | None = None,
    settings: Settings | None = None,
) -> UserPublic:
    settings = settings or get_settings()
    user = get_user_by_id(user_id, settings=settings)
    if user is None:
        raise LookupError("User not found")

    fields: list[str] = []
    values: list[object] = []
    if role is not None:
        fields.append("role = ?")
        values.append(role.value)
    if is_active is not None:
        fields.append("is_active = ?")
        values.append(1 if is_active else 0)
    if password is not None:
        validate_password(password, settings=settings)
        fields.append("password_hash = ?")
        values.append(hash_password(password))
    if not fields:
        return user

    values.append(user_id)
    with get_connection(settings) as conn:
        conn.execute(
            f"UPDATE users SET {', '.join(fields)} WHERE id = ?",
            values,
        )
    updated = get_user_by_id(user_id, settings=settings)
    if updated is None:
        raise RuntimeError("Failed to load updated user")
    return updated
