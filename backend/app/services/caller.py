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


_FIELD_LABELS = {
    "patient_name": "the patient's full legal name",
    "date_of_birth": "the patient's date of birth",
    "phone_number": "a callback phone number",
    "referring_physician": "the referring physician's name",
    "reason_for_referral": "the reason for the referral",
    "insurance_id": "the insurance ID",
    "clinic_name": "the clinic name",
}

_OVERRIDE_AGENTS_READY: set[str] = set()


def _client(settings: Settings) -> ElevenLabs:
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured")
    return ElevenLabs(api_key=settings.elevenlabs_api_key)


def _field_value(record: CaseRecord, *names: str) -> str | None:
    for name in names:
        field = record.fields.get(name)
        if field and field.value and str(field.value).strip():
            return str(field.value).strip()
    return None


def _doctor_label(raw: str) -> str:
    name = raw.strip()
    lowered = name.lower()
    if lowered.startswith(("dr.", "dr ", "doctor ")):
        return name
    return f"Dr. {name}"


def _caller_identity(record: CaseRecord) -> str:
    physician = _field_value(
        record,
        "referring_physician",
        "physician",
        "doctor",
        "doctor_name",
        "provider_name",
    )
    clinic = _field_value(
        record,
        "clinic_name",
        "clinic",
        "facility_name",
        "practice_name",
        "organization",
        "hospital_name",
    )
    if physician and clinic:
        return f"{clinic}, calling for {_doctor_label(physician)}"
    if physician:
        return f"{_doctor_label(physician)}'s office"
    if clinic:
        return clinic
    return "the clinic fax intake team"


def _field_label(name: str) -> str:
    if name in _FIELD_LABELS:
        return _FIELD_LABELS[name]
    return name.replace("_", " ")


def _missing_questions(record: CaseRecord) -> list[str]:
    names = record.missing_required or []
    return [_field_label(n) for n in names]


def build_first_message(record: CaseRecord) -> str:
    identity = _caller_identity(record)
    patient = _field_value(record, "patient_name")
    questions = _missing_questions(record)
    about = f" for patient {patient}" if patient else ""
    if questions:
        need = (
            "I need to collect a few missing details from a fax we received"
            f"{about}: {'; '.join(questions)}."
        )
    else:
        need = (
            "I'm calling about a fax we received"
            f"{about} and need to confirm a couple of details."
        )
    return (
        f"Hello, this is the fax intake assistant with {identity}. "
        f"{need} Do you have a moment to help?"
    )


def build_system_prompt(record: CaseRecord) -> str:
    identity = _caller_identity(record)
    patient = _field_value(record, "patient_name") or "the patient"
    questions = _missing_questions(record)
    missing_block = (
        "\n".join(f"- {q}" for q in questions)
        if questions
        else "- Confirm any unclear details from the fax"
    )
    known = []
    for name, field in record.fields.items():
        if field.value and field.confidence >= 0.7:
            known.append(f"- {_field_label(name)}: {field.value}")
    known_block = "\n".join(known) if known else "- none confirmed yet"
    reason = record.call.reason or (
        "We received a referral/intake fax with incomplete information and need "
        "the missing items before we can process it."
    )
    return f"""You are a polite outbound fax intake phone assistant for {identity}.

Why you are calling (state this clearly if asked, and briefly in your opening):
{reason}
Patient this call is about: {patient}

Your ONLY job is to collect these missing items, one at a time:
{missing_block}

Already known from the fax (do not re-ask unless the person corrects you):
{known_block}

Rules:
- Introduce yourself as calling from {identity}.
- You placed this outbound call — never ask why they called you.
- Explain you are calling because a fax was incomplete / missing details.
- Ask only for the missing items listed above. Do not invent values.
- Confirm spelling for names, IDs, and unusual words.
- Be brief. Thank them and end when finished or if they decline.
- If they cannot provide an item, note that and move to the next one.
"""


def build_call_context(record: CaseRecord) -> dict[str, str]:
    known = []
    for name, field in record.fields.items():
        if field.value and field.confidence >= 0.7:
            known.append(f"{name}={field.value}")
    questions = _missing_questions(record)
    return {
        "case_id": record.id,
        "patient_name": _field_value(record, "patient_name") or "unknown",
        "caller_identity": _caller_identity(record),
        "missing_fields": ", ".join(record.missing_required) or "none",
        "missing_questions": "; ".join(questions) or "none",
        "known_facts": "; ".join(known) or "none",
        "call_reason": record.call.reason
        or "collect missing details from an incomplete fax",
        "first_message": build_first_message(record),
    }


def _ensure_agent_allows_overrides(client: ElevenLabs, agent_id: str) -> None:
    if agent_id in _OVERRIDE_AGENTS_READY:
        return
    client.conversational_ai.agents.update(
        agent_id=agent_id,
        platform_settings={
            "overrides": {
                "conversation_config_override": {
                    "agent": {
                        "first_message": True,
                        "prompt": {"prompt": True},
                    }
                }
            }
        },
    )
    _OVERRIDE_AGENTS_READY.add(agent_id)


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
    try:
        _ensure_agent_allows_overrides(client, settings.elevenlabs_agent_id)
    except Exception:
        logger.exception(
            "Could not enable ElevenLabs first_message/prompt overrides on agent %s",
            settings.elevenlabs_agent_id,
        )

    dynamic_vars = build_call_context(record)
    first_message = build_first_message(record)
    system_prompt = build_system_prompt(record)

    response = client.conversational_ai.twilio.outbound_call(
        agent_id=settings.elevenlabs_agent_id,
        agent_phone_number_id=settings.elevenlabs_agent_phone_number_id,
        to_number=to_number,
        conversation_initiation_client_data={
            "dynamic_variables": dynamic_vars,
            "conversation_config_override": {
                "agent": {
                    "first_message": first_message,
                    "prompt": {"prompt": system_prompt},
                }
            },
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
