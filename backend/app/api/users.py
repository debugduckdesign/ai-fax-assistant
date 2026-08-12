from fastapi import APIRouter, Depends, HTTPException

from app.models.schemas import UserCreate, UserPublic, UserUpdate
from app.security import require_admin
from app.services import users

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserPublic])
async def list_users(_: UserPublic = Depends(require_admin)) -> list[UserPublic]:
    return users.list_users()


@router.post("", response_model=UserPublic)
async def create_user(
    body: UserCreate, _: UserPublic = Depends(require_admin)
) -> UserPublic:
    try:
        return users.create_user(body.username, body.password, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{user_id}", response_model=UserPublic)
async def update_user(
    user_id: str,
    body: UserUpdate,
    actor: UserPublic = Depends(require_admin),
) -> UserPublic:
    if actor.id == user_id and body.is_active is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    try:
        return users.update_user(
            user_id,
            role=body.role,
            is_active=body.is_active,
            password=body.password,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
