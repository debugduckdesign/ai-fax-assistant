from fastapi import APIRouter, Depends, HTTPException

from app.config import BACKEND_DIR, get_settings
from app.models.schemas import RequirementsResponse, RequirementsUpdate, UserPublic
from app.security import require_admin
from app.services import requirements as requirements_service

router = APIRouter(prefix="/api/requirements", tags=["requirements"])


def _public_requirements_path() -> str:
    settings = get_settings()
    try:
        return str(settings.requirements_path.relative_to(BACKEND_DIR))
    except ValueError:
        return settings.requirements_path.name


@router.get("", response_model=RequirementsResponse)
async def get_requirements(
    _: UserPublic = Depends(require_admin),
) -> RequirementsResponse:
    settings = get_settings()
    try:
        content = requirements_service.load_requirements(settings)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Requirements not found") from exc
    return RequirementsResponse(content=content, path=_public_requirements_path())


@router.put("", response_model=RequirementsResponse)
async def put_requirements(
    body: RequirementsUpdate,
    _: UserPublic = Depends(require_admin),
) -> RequirementsResponse:
    settings = get_settings()
    if len(body.content) > settings.max_requirements_chars:
        raise HTTPException(status_code=413, detail="Requirements document too large")
    content = requirements_service.save_requirements(body.content, settings)
    return RequirementsResponse(content=content, path=_public_requirements_path())
