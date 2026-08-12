import logging

from app.config import get_settings
from app.models.schemas import CaseStatus
from app.services import call_history, caller, case_store, extractor
from app.services.case_writer import write_case_artifacts

logger = logging.getLogger(__name__)


async def run_extraction(case_id: str) -> None:
    settings = get_settings()
    record = case_store.load_case(case_id, settings=settings)
    record.status = CaseStatus.EXTRACTING
    write_case_artifacts(record)

    try:
        scan = case_store.scan_path(case_id, settings=settings)
        result = extractor.extract_from_scan(scan, settings=settings)

        record.fields = result.fields
        record.missing_required = result.missing_required
        record.call_recommended = result.call_recommended
        record.call.to = result.call_to
        record.call.reason = result.call_reason
        record.error = None

        if not result.missing_required:
            record.status = CaseStatus.COMPLETE
            record.call_recommended = False
        elif result.call_recommended and result.call_to:
            record.status = CaseStatus.AWAITING_CALL
        else:
            record.status = CaseStatus.NEEDS_HUMAN

        write_case_artifacts(record)
    except Exception:
        logger.exception("Extraction failed for case %s", case_id)
        record.status = CaseStatus.ERROR
        record.error = "Extraction failed"
        write_case_artifacts(record)


async def place_call(case_id: str, placed_by_user_id: str | None = None) -> None:
    settings = get_settings()
    record = case_store.load_case(case_id, settings=settings)

    if record.status not in {
        CaseStatus.AWAITING_CALL,
        CaseStatus.NEEDS_HUMAN,
        CaseStatus.COMPLETE,
        CaseStatus.CALLING,
    }:
        raise RuntimeError(
            f"Case {case_id} is not ready for calling (status={record.status})"
        )

    if not record.call.to and record.call_recommended:
        raise RuntimeError("No phone number available to call")

    record.status = CaseStatus.CALLING
    record.call.status = "initiating"
    write_case_artifacts(record)

    try:
        conversation_id = caller.start_outbound_call(record, settings=settings)
        record.call.conversation_id = conversation_id
        record.call.status = "in_progress"
        write_case_artifacts(record)
        call_history.record_call_placed(
            case_id=case_id,
            user_id=placed_by_user_id,
            conversation_id=conversation_id,
            to_number=record.call.to,
            reason=record.call.reason,
            status="in_progress",
            settings=settings,
        )
    except Exception:
        logger.exception("Outbound call failed for case %s", case_id)
        record.status = CaseStatus.ERROR
        record.call.status = "failed"
        record.error = "Outbound call failed"
        write_case_artifacts(record)
        call_history.record_call_placed(
            case_id=case_id,
            user_id=placed_by_user_id,
            conversation_id=record.call.conversation_id,
            to_number=record.call.to,
            reason=record.call.reason,
            status="failed",
            settings=settings,
        )
        raise


async def complete_call_from_conversation(conversation_id: str) -> None:
    settings = get_settings()
    record = case_store.find_case_by_conversation_id(conversation_id, settings=settings)
    if record is None:
        raise FileNotFoundError(f"No case found for conversation_id={conversation_id}")

    transcript = caller.fetch_conversation_transcript(
        conversation_id, settings=settings
    )
    record.call.transcript = transcript or record.call.transcript
    record.call.status = "completed"

    current = caller.extraction_from_case(record)
    if transcript:
        merged = extractor.merge_transcript_into_fields(
            current, transcript, settings=settings
        )
        record.fields = merged.fields
        record.missing_required = merged.missing_required
        record.call_recommended = False

    if record.missing_required:
        record.status = CaseStatus.NEEDS_HUMAN
    else:
        record.status = CaseStatus.COMPLETE

    record.error = None
    write_case_artifacts(record)
    call_history.update_call_by_conversation(
        conversation_id,
        status="completed",
        transcript=record.call.transcript,
        settings=settings,
    )
