from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.config import Settings, get_settings
from app.db import get_connection
from app.models.schemas import CallEvent


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _row_to_event(row) -> CallEvent:
    return CallEvent(
        id=row["id"],
        case_id=row["case_id"],
        user_id=row["user_id"],
        username=row["username"] if "username" in row.keys() else None,
        conversation_id=row["conversation_id"],
        to_number=row["to_number"],
        status=row["status"],
        reason=row["reason"],
        transcript_excerpt=row["transcript_excerpt"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def record_call_placed(
    *,
    case_id: str,
    user_id: str | None,
    conversation_id: str | None,
    to_number: str | None,
    reason: str | None = None,
    status: str = "in_progress",
    settings: Settings | None = None,
) -> CallEvent:
    settings = settings or get_settings()
    now = _utcnow()
    event_id = uuid.uuid4().hex
    with get_connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO call_events (
                id, case_id, user_id, conversation_id, to_number,
                status, reason, transcript_excerpt, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                event_id,
                case_id,
                user_id,
                conversation_id,
                to_number,
                status,
                reason,
                now,
                now,
            ),
        )
    events = list_calls(case_id=case_id, limit=1, settings=settings)
    for event in events:
        if event.id == event_id:
            return event
    return CallEvent(
        id=event_id,
        case_id=case_id,
        user_id=user_id,
        conversation_id=conversation_id,
        to_number=to_number,
        status=status,
        reason=reason,
        created_at=now,
        updated_at=now,
    )


def update_call_by_conversation(
    conversation_id: str,
    *,
    status: str,
    transcript: str | None = None,
    settings: Settings | None = None,
) -> CallEvent | None:
    settings = settings or get_settings()
    excerpt = None
    if transcript:
        excerpt = transcript[:500]
    now = _utcnow()
    with get_connection(settings) as conn:
        row = conn.execute(
            """
            SELECT id FROM call_events
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            """
            UPDATE call_events
            SET status = ?, transcript_excerpt = COALESCE(?, transcript_excerpt),
                updated_at = ?
            WHERE id = ?
            """,
            (status, excerpt, now, row["id"]),
        )
        event_id = row["id"]
    for event in list_calls(limit=200, settings=settings):
        if event.id == event_id:
            return event
    return None


def update_call_for_case(
    case_id: str,
    *,
    status: str,
    conversation_id: str | None = None,
    transcript: str | None = None,
    settings: Settings | None = None,
) -> CallEvent | None:
    settings = settings or get_settings()
    excerpt = transcript[:500] if transcript else None
    now = _utcnow()
    with get_connection(settings) as conn:
        row = conn.execute(
            """
            SELECT id FROM call_events
            WHERE case_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (case_id,),
        ).fetchone()
        if not row:
            return None
        if conversation_id:
            conn.execute(
                """
                UPDATE call_events
                SET status = ?, conversation_id = COALESCE(?, conversation_id),
                    transcript_excerpt = COALESCE(?, transcript_excerpt),
                    updated_at = ?
                WHERE id = ?
                """,
                (status, conversation_id, excerpt, now, row["id"]),
            )
        else:
            conn.execute(
                """
                UPDATE call_events
                SET status = ?,
                    transcript_excerpt = COALESCE(?, transcript_excerpt),
                    updated_at = ?
                WHERE id = ?
                """,
                (status, excerpt, now, row["id"]),
            )
    for event in list_calls(case_id=case_id, limit=1, settings=settings):
        return event
    return None


def list_calls(
    *,
    user_id: str | None = None,
    case_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    settings: Settings | None = None,
) -> list[CallEvent]:
    settings = settings or get_settings()
    clauses: list[str] = []
    values: list[object] = []
    if user_id:
        clauses.append("c.user_id = ?")
        values.append(user_id)
    if case_id:
        clauses.append("c.case_id = ?")
        values.append(case_id)
    if status:
        clauses.append("c.status = ?")
        values.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    values.append(max(1, min(limit, 500)))
    with get_connection(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT c.*, u.username AS username
            FROM call_events c
            LEFT JOIN users u ON u.id = c.user_id
            {where}
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
    return [_row_to_event(r) for r in rows]
