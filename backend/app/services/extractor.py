import base64
import json
import logging
import re
from pathlib import Path

import anthropic
import pymupdf

from app.config import Settings, get_settings
from app.models.schemas import ExtractionResult, FieldValue
from app.services.requirements import load_requirements

logger = logging.getLogger(__name__)

EXTRACT_SYSTEM = """You are a medical fax intake assistant.
Extract fields from the fax scan image(s) according to the requirements document.
Return ONLY valid JSON matching this schema:
{
  "fields": {
    "<field_name>": {
      "value": "<string or null>",
      "confidence": 0.0-1.0,
      "source": "ocr"
    }
  },
  "missing_required": ["<field_name>", ...],
  "call_recommended": true/false,
  "call_to": "<E.164 phone or null>",
  "call_reason": "<why call or null>"
}
Rules:
- Include every field mentioned under Required fields in the requirements.
- Treat confidence below the given threshold as missing.
- Never invent phone numbers.
- Prefer phone_number from the fax for call_to when a callback is warranted.
- source must be "ocr" for fax-extracted values.
"""

MERGE_SYSTEM = """You merge a phone-call transcript into an existing fax intake case.
Update ONLY missing or low-confidence fields using information from the transcript.
Return ONLY valid JSON:
{
  "fields": {
    "<field_name>": {
      "value": "<string or null>",
      "confidence": 0.0-1.0,
      "source": "call"|"ocr"|"unchanged"
    }
  },
  "missing_required": ["<field_name>", ...],
  "call_recommended": false,
  "call_to": null,
  "call_reason": null
}
Keep existing high-confidence fax values unless the caller clearly corrects them.
For newly filled values from the call, set source to "call".
"""


def _media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
    }.get(suffix, "application/octet-stream")


def pdf_to_png_bytes(pdf_path: Path, max_pages: int = 3) -> list[bytes]:
    doc = pymupdf.open(pdf_path)
    images: list[bytes] = []
    try:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
            images.append(pix.tobytes("png"))
    finally:
        doc.close()
    return images


def load_image_payloads(scan_path: Path) -> list[dict]:
    media = _media_type(scan_path)
    payloads: list[dict] = []

    if media == "application/pdf":
        for png in pdf_to_png_bytes(scan_path):
            payloads.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.standard_b64encode(png).decode("ascii"),
                    },
                }
            )
    elif media.startswith("image/"):
        data = base64.standard_b64encode(scan_path.read_bytes()).decode("ascii")
        payloads.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media,
                    "data": data,
                },
            }
        )
    else:
        raise ValueError(f"Unsupported scan type: {media}")

    if not payloads:
        raise ValueError("No pages/images found in scan")
    return payloads


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def _parse_extraction(raw: dict, threshold: float) -> ExtractionResult:
    fields: dict[str, FieldValue] = {}
    for name, value in (raw.get("fields") or {}).items():
        if isinstance(value, dict):
            fields[name] = FieldValue(
                value=value.get("value"),
                confidence=float(value.get("confidence") or 0.0),
                source=str(value.get("source") or "ocr"),
            )
        else:
            fields[name] = FieldValue(value=str(value) if value is not None else None)

    missing = list(raw.get("missing_required") or [])
    recomputed: list[str] = []
    for name in missing:
        field = fields.get(name)
        if (
            field is None
            or not field.value
            or not str(field.value).strip()
            or field.confidence < threshold
        ):
            recomputed.append(name)

    return ExtractionResult(
        fields=fields,
        missing_required=recomputed,
        call_recommended=bool(raw.get("call_recommended")),
        call_to=raw.get("call_to"),
        call_reason=raw.get("call_reason"),
    )


def extract_from_scan(
    scan_path: Path, settings: Settings | None = None
) -> ExtractionResult:
    settings = settings or get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    requirements = load_requirements(settings)
    images = load_image_payloads(scan_path)
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    user_content: list[dict] = [
        *images,
        {
            "type": "text",
            "text": (
                f"Confidence threshold: {settings.confidence_threshold}\n\n"
                f"Requirements document:\n\n{requirements}\n\n"
                "Extract the fields now."
            ),
        },
    ]

    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=4096,
        system=EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    raw = _extract_json(text)
    return _parse_extraction(raw, settings.confidence_threshold)


def merge_transcript_into_fields(
    current: ExtractionResult,
    transcript: str,
    settings: Settings | None = None,
) -> ExtractionResult:
    settings = settings or get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    requirements = load_requirements(settings)
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    payload = {
        "current_fields": {k: v.model_dump() for k, v in current.fields.items()},
        "missing_required": current.missing_required,
        "transcript": transcript,
        "confidence_threshold": settings.confidence_threshold,
    }

    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=4096,
        system=MERGE_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Requirements:\n\n{requirements}\n\n"
                    f"Case data and transcript:\n\n{json.dumps(payload, indent=2)}"
                ),
            }
        ],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    raw = _extract_json(text)
    merged = _parse_extraction(raw, settings.confidence_threshold)

    for name, field in merged.fields.items():
        if field.source == "unchanged" and name in current.fields:
            merged.fields[name] = current.fields[name]
        elif field.source == "unchanged":
            field.source = "ocr"

    for name in current.missing_required:
        new_field = merged.fields.get(name)
        old_field = current.fields.get(name)
        if (
            new_field
            and new_field.value
            and (
                not old_field
                or not old_field.value
                or old_field.confidence < settings.confidence_threshold
            )
            and new_field.source == "ocr"
        ):
            new_field.source = "call"

    for name, field in current.fields.items():
        if name not in merged.fields:
            merged.fields[name] = field

    return merged
