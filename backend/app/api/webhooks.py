import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request

from app.config import get_settings
from app.security import verify_elevenlabs_webhook
from app.services.pipeline import complete_call_from_conversation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _extract_conversation_id(payload: dict[str, Any]) -> str | None:
    if payload.get("conversation_id"):
        return str(payload["conversation_id"])
    data = payload.get("data") or {}
    if isinstance(data, dict):
        if data.get("conversation_id"):
            return str(data["conversation_id"])
        conversation = data.get("conversation") or {}
        if isinstance(conversation, dict) and conversation.get("id"):
            return str(conversation["id"])
    conversation = payload.get("conversation") or {}
    if isinstance(conversation, dict) and conversation.get("id"):
        return str(conversation["id"])
    return None


def _is_completion_event(payload: dict[str, Any]) -> bool:
    event = (
        payload.get("type") or payload.get("event") or payload.get("event_type") or ""
    )
    event = str(event).lower()
    if not event:
        return True
    markers = (
        "conversation.ended",
        "conversation_ended",
        "post_call",
        "call_ended",
        "completed",
        "done",
    )
    return any(m in event for m in markers)


@router.post("/elevenlabs")
async def elevenlabs_webhook(
    request: Request, background_tasks: BackgroundTasks
) -> dict[str, str]:
    settings = get_settings()
    raw = await request.body()
    signature = request.headers.get("elevenlabs-signature")
    if not settings.elevenlabs_webhook_secret and settings.allow_insecure_webhooks:
        logger.warning(
            "ALLOW_INSECURE_WEBHOOKS enabled; accepting webhook without HMAC"
        )

    payload = verify_elevenlabs_webhook(raw, signature, settings)
    if not isinstance(payload, dict):
        payload = {}

    conversation_id = _extract_conversation_id(payload)
    logger.info(
        "ElevenLabs webhook type=%s conversation_id=%s",
        payload.get("type") or payload.get("event") or "unknown",
        conversation_id or "missing",
    )

    if not _is_completion_event(payload):
        return {"status": "ignored"}
    if not conversation_id:
        return {"status": "missing_conversation_id"}

    background_tasks.add_task(complete_call_from_conversation, conversation_id)
    return {"status": "accepted", "conversation_id": conversation_id}
