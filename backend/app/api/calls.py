from fastapi import APIRouter, Depends, Query

from app.models.schemas import CallEvent, UserPublic, UserRole
from app.security import require_user
from app.services import call_history

router = APIRouter(prefix="/api/calls", tags=["calls"])


@router.get("", response_model=list[CallEvent])
async def list_call_history(
    case_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: UserPublic = Depends(require_user),
) -> list[CallEvent]:
    filter_user = user_id
    if user.role != UserRole.ADMIN:
        filter_user = user.id
    return call_history.list_calls(
        user_id=filter_user,
        case_id=case_id,
        status=status,
        limit=limit,
    )
