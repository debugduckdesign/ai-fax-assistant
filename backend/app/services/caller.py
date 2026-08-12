import logging
from dataclasses import dataclass
from typing import Any

import httpx
from elevenlabs import ElevenLabs

from app.config import Settings, get_settings
from app.models.schemas import CaseRecord, ExtractionResult

logger = logging.getLogger(__name__)

ACTIVE_CONVERSATION_STATUSES = frozenset(
    {"initiated", "in-progress", "in_progress", "processing"}
)
FAILED_CONVERSATION_STATUSES = frozenset({"failed"})
DONE_CONVERSATION_STATUSES = frozenset({"done", "completed"})


@dataclass(frozen=True)
class ConversationOutcome:
    status: str
    transcript: str
    termination_reason: str | None = None
    call_successful: str | None = None

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_CONVERSATION_STATUSES

    @property
    def is_done(self) -> bool:
        return self.status in DONE_CONVERSATION_STATUSES

    @property
    def is_failed(self) -> bool:
        return self.status in FAILED_CONVERSATION_STATUSES

    @property
    def is_canceled(self) -> bool:
        reason = (self.termination_reason or "").lower()
        return any(
            token in reason
            for token in (
                "cancel",
                "busy",
                "no-answer",
                "no_answer",
                "not_answered",
                "rejected",
            )
        )

    @property
    def is_unsuccessful(self) -> bool:
        """Terminal call that did not produce a usable conversation."""
        if self.is_failed:
            return True
        has_transcript = bool(self.transcript.strip())
        if self.is_canceled and not has_transcript:
            return True
        if self.is_done and not has_transcript:
            if (self.call_successful or "").lower() == "failure":
                return True
        return False

    @property
    def call_status_label(self) -> str:
        reason = (self.termination_reason or "").lower()
        if "cancel" in reason:
            return "canceled"
        return "failed"

    @property
    def error_message(self) -> str:
        if self.termination_reason:
            return f"Call ended: {self.termination_reason}"
        if self.is_canceled:
            return "Call was canceled"
        return "Call failed"


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
    # Overrides need agent Security permissions; we only pass dynamic variables.
    response = client.conversational_ai.twilio.outbound_call(
        agent_id=settings.elevenlabs_agent_id,
        agent_phone_number_id=settings.elevenlabs_agent_phone_number_id,
        to_number=to_number,
        conversation_initiation_client_data={
            "dynamic_variables": build_call_context(record),
        },
    )

    conversation_id = getattr(response, "conversation_id", None)
    if conversation_id is None and isinstance(response, dict):
        conversation_id = response.get("conversation_id")
    return conversation_id


def _conversation_payload(details: Any) -> dict[str, Any]:
    if details is None:
        return {}
    if hasattr(details, "model_dump"):
        data = details.model_dump()
    elif isinstance(details, dict):
        data = details
    else:
        data = getattr(details, "__dict__", {}) or {}
    return data if isinstance(data, dict) else {}


def _fetch_conversation_payload(
    conversation_id: str, settings: Settings
) -> dict[str, Any]:
    client = _client(settings)
    try:
        details = client.conversational_ai.conversations.get(conversation_id)
        data = _conversation_payload(details)
        if data:
            return data
    except Exception:
        logger.exception("Failed to fetch conversation %s via SDK", conversation_id)

    url = f"https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}"
    headers = {"xi-api-key": settings.elevenlabs_api_key}
    with httpx.Client(timeout=30.0) as http:
        resp = http.get(url, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
    return payload if isinstance(payload, dict) else {}


def fetch_conversation_outcome(
    conversation_id: str, settings: Settings | None = None
) -> ConversationOutcome:
    settings = settings or get_settings()
    data = _fetch_conversation_payload(conversation_id, settings)
    status = str(data.get("status") or "").strip().lower() or "unknown"
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    analysis = data.get("analysis") or {}
    if not isinstance(analysis, dict):
        analysis = {}
    termination_reason = (
        metadata.get("termination_reason")
        or data.get("termination_reason")
        or analysis.get("termination_reason")
    )
    if termination_reason is not None:
        termination_reason = str(termination_reason)
    call_successful = analysis.get("call_successful")
    if call_successful is not None:
        call_successful = str(call_successful)
    return ConversationOutcome(
        status=status,
        transcript=_transcript_from_details(data),
        termination_reason=termination_reason,
        call_successful=call_successful,
    )


def fetch_conversation_transcript(
    conversation_id: str, settings: Settings | None = None
) -> str:
    return fetch_conversation_outcome(conversation_id, settings=settings).transcript


def _transcript_from_details(details: Any) -> str:
    data = _conversation_payload(details)
    if not data:
        return ""

    parts: list[str] = []
    analysis = data.get("analysis") or {}
    if not isinstance(analysis, dict):
        analysis = {}
    transcript = data.get("transcript") or analysis.get("transcript")
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
