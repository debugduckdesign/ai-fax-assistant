from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.config import get_settings
from app.models.schemas import LoginRequest, UserPublic
from app.security import require_user
from app.services import sessions, users

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_key(request: Request, username: str) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return f"{ip}:{username.strip().lower()}"


@router.post("/login", response_model=UserPublic)
async def login(body: LoginRequest, request: Request, response: Response) -> UserPublic:
    settings = get_settings()
    if not sessions.allow_login_attempt(
        _client_key(request, body.username), settings=settings
    ):
        raise HTTPException(status_code=429, detail="Too many login attempts")

    user = users.authenticate(body.username, body.password, settings=settings)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    session_id = sessions.create_session(
        {"user_id": user.id, "role": user.role.value},
        settings=settings,
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    return user


@router.post("/logout")
async def logout(request: Request, response: Response):
    settings = get_settings()
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        sessions.delete_session(session_id, settings=settings)
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return {"status": "ok"}


@router.get("/me", response_model=UserPublic)
async def me(user: UserPublic = Depends(require_user)) -> UserPublic:
    return user
