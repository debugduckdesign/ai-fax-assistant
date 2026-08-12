import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import get_settings
from app.models.schemas import (
    CaseRecord,
    CaseStatus,
    CaseSummary,
    PlaceCallResponse,
    UserPublic,
)
from app.security import (
    require_user,
    safe_filename,
    sniff_media_type,
    validate_case_id,
)
from app.services import case_store
from app.services.pipeline import place_call, run_extraction

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.post("", response_model=CaseRecord)
async def create_case(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: UserPublic = Depends(require_user),
) -> CaseRecord:
    settings = get_settings()
    filename = safe_filename(file.filename or "scan.bin")

    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    sniffed = sniff_media_type(data)
    if sniffed is None:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    created_by = None if user.id == "api-key" else user.id
    record = case_store.create_case(
        scan_bytes=data,
        filename=filename,
        content_type=sniffed,
        created_by_user_id=created_by,
    )
    background_tasks.add_task(run_extraction, record.id)
    return record


@router.get("", response_model=list[CaseSummary])
async def list_cases(_: UserPublic = Depends(require_user)) -> list[CaseSummary]:
    cases = case_store.list_cases()
    return [
        CaseSummary(
            id=c.id,
            status=c.status,
            created_at=c.created_at,
            updated_at=c.updated_at,
            scan_filename=c.scan_filename,
            call_recommended=c.call_recommended,
            missing_required=c.missing_required,
            call_to=c.call.to,
            created_by_user_id=c.created_by_user_id,
        )
        for c in cases
    ]


@router.get("/{case_id}", response_model=CaseRecord)
async def get_case(case_id: str, _: UserPublic = Depends(require_user)) -> CaseRecord:
    case_id = validate_case_id(case_id)
    try:
        return case_store.load_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc


@router.get("/{case_id}/scan")
async def get_scan(case_id: str, _: UserPublic = Depends(require_user)) -> FileResponse:
    case_id = validate_case_id(case_id)
    try:
        path = case_store.scan_path(case_id)
        record = case_store.load_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc

    media = record.scan_content_type or "application/octet-stream"
    return FileResponse(path, media_type=media, filename=record.scan_filename)


@router.post("/{case_id}/call", response_model=PlaceCallResponse)
async def start_call(
    case_id: str, user: UserPublic = Depends(require_user)
) -> PlaceCallResponse:
    case_id = validate_case_id(case_id)
    try:
        record = case_store.load_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc

    if not record.call.to:
        raise HTTPException(
            status_code=400, detail="No phone number available for this case"
        )
    if record.status == CaseStatus.CALLING and record.call.conversation_id:
        return PlaceCallResponse(
            case_id=case_id,
            conversation_id=record.call.conversation_id,
            status=record.status,
            message="Call already in progress",
        )
    if record.status not in {
        CaseStatus.AWAITING_CALL,
        CaseStatus.NEEDS_HUMAN,
        CaseStatus.COMPLETE,
    }:
        raise HTTPException(
            status_code=400,
            detail=f"Case status {record.status.value} cannot place a call",
        )

    placed_by = None if user.id == "api-key" else user.id
    try:
        await place_call(case_id, placed_by_user_id=placed_by)
    except Exception as exc:
        logger.exception("Outbound call failed for case %s", case_id)
        raise HTTPException(
            status_code=502, detail="Failed to place outbound call"
        ) from exc

    updated = case_store.load_case(case_id)
    asyncio.create_task(_poll_conversation(case_id))

    return PlaceCallResponse(
        case_id=case_id,
        conversation_id=updated.call.conversation_id,
        status=updated.status,
        message="Outbound call initiated",
    )


async def _poll_conversation(
    case_id: str, attempts: int = 40, delay: float = 15.0
) -> None:
    from app.services.pipeline import complete_call_from_conversation

    for _ in range(attempts):
        await asyncio.sleep(delay)
        try:
            record = case_store.load_case(case_id)
        except FileNotFoundError:
            return
        if record.status != CaseStatus.CALLING:
            return
        if not record.call.conversation_id:
            return
        try:
            await complete_call_from_conversation(record.call.conversation_id)
            updated = case_store.load_case(case_id)
            if updated.status != CaseStatus.CALLING:
                return
        except Exception:
            logger.exception("Poll merge failed for case %s", case_id)
