import logging
from typing import Any

import httpx
from elevenlabs import ElevenLabs

from app.config import Settings, get_settings
from app.models.schemas import CaseRecord, ExtractionResult

logger = logging.getLogger(__name__)


def _client(settings: Settings) -> ElevenLabs:
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured")
    return ElevenLabs(api_key=settings.elevenlabs_api_key)


def build_call_context(record: CaseRecord) -> dict[str, str]:
    known = []
    for name, field in record.fields.items():
        if field.value and field.confidence >= 0.7:
            known.append(f"{name}={field.value}")
    missing = ", ".join(record.missing_required) or "none"
    return {
        "case_id": record.id,
        "patient_name": (
            (record.fields.get("patient_name").value or "unknown")
            if record.fields.get("patient_name")
            else "unknown"
        ),
        "missing_fields": missing,
        "known_facts": "; ".join(known) or "none",
        "call_reason": record.call.reason or "collect missing fax fields",
    }


def start_outbound_call(
    record: CaseRecord, settings: Settings | None = None
) -> str | None:
    settings = settings or get_settings()
    if not settings.elevenlabs_agent_id:
        raise RuntimeError("ELEVENLABS_AGENT_ID is not configured")
    if not settings.elevenlabs_agent_phone_number_id:
        raise RuntimeError("ELEVENLABS_AGENT_PHONE_NUMBER_ID is not configured")

    to_number = record.call.to
    if not to_number:
        raise RuntimeError("No call_to phone number available for this case")

    client = _client(settings)
    dynamic_vars = build_call_context(record)

    response = client.conversational_ai.twilio.outbound_call(
        agent_id=settings.elevenlabs_agent_id,
        agent_phone_number_id=settings.elevenlabs_agent_phone_number_id,
        to_number=to_number,
        conversation_initiation_client_data={
            "dynamic_variables": dynamic_vars,
            "conversation_config_override": {
                "agent": {
                    "first_message": (
                        "Hello, this is the clinic fax assistant. "
                        "I'm calling about a fax we received and need a few details."
                    ),
                    "prompt": {
                        "prompt": (
                            "You are a polite clinic fax intake assistant. "
                            "Collect only these missing fields: {{missing_fields}}. "
                            "Known facts: {{known_facts}}. "
                            "Confirm spelling for names and IDs. Be brief."
                        )
                    },
                }
            },
        },
    )

    conversation_id = getattr(response, "conversation_id", None)
    if conversation_id is None and isinstance(response, dict):
        conversation_id = response.get("conversation_id")
    return conversation_id


def fetch_conversation_transcript(
    conversation_id: str, settings: Settings | None = None
) -> str:
    settings = settings or get_settings()
    client = _client(settings)

    try:
        details = client.conversational_ai.conversations.get(conversation_id)
    except Exception:
        logger.exception("Failed to fetch conversation %s via SDK", conversation_id)
        details = None

    transcript = _transcript_from_details(details)
    if transcript:
        return transcript

    url = f"https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}"
    headers = {"xi-api-key": settings.elevenlabs_api_key}
    with httpx.Client(timeout=30.0) as http:
        resp = http.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return _transcript_from_details(data)


def _transcript_from_details(details: Any) -> str:
    if details is None:
        return ""

    if hasattr(details, "model_dump"):
        data = details.model_dump()
    elif isinstance(details, dict):
        data = details
    else:
        data = getattr(details, "__dict__", {}) or {}

    parts: list[str] = []
    transcript = data.get("transcript") or data.get("analysis", {}).get("transcript")
    if isinstance(transcript, str) and transcript.strip():
        return transcript.strip()

    if isinstance(transcript, list):
        for turn in transcript:
            if isinstance(turn, dict):
                role = turn.get("role") or turn.get("speaker") or "unknown"
                text = turn.get("message") or turn.get("text") or ""
                if text:
                    parts.append(f"{role}: {text}")
            else:
                role = getattr(turn, "role", None) or getattr(
                    turn, "speaker", "unknown"
                )
                text = getattr(turn, "message", None) or getattr(turn, "text", "")
                if text:
                    parts.append(f"{role}: {text}")

    messages = data.get("messages") or []
    if not parts and isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", "unknown")
                text = msg.get("message") or msg.get("content") or ""
                if text:
                    parts.append(f"{role}: {text}")

    return "\n".join(parts).strip()


def extraction_from_case(record: CaseRecord) -> ExtractionResult:
    return ExtractionResult(
        fields=record.fields,
        missing_required=record.missing_required,
        call_recommended=record.call_recommended,
        call_to=record.call.to,
        call_reason=record.call.reason,
    )
