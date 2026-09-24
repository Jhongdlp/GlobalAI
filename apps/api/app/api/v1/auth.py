from fastapi import APIRouter, Request, Response
from sqlalchemy import func, select

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.db import SessionDep
from app.core.errors import AppError, UnauthorizedError
from app.core.rate_limit import login_limiter
from app.core.security import DUMMY_HASH, create_access_token, verify_password
from app.models import User
from app.schemas.auth import LoginIn, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


class TooManyAttemptsError(AppError):
    status_code = 429
    code = "too_many_attempts"


@router.post("/login")
async def login(
    body: LoginIn, request: Request, response: Response, session: SessionDep
) -> UserOut:
    email = body.email.lower()
    key = f"{request.client.host if request.client else '-'}:{email}"
    if login_limiter.is_blocked(key):
        raise TooManyAttemptsError("Demasiados intentos. Espera unos minutos e inténtalo de nuevo")

    user = await session.scalar(select(User).where(func.lower(User.email) == email))
    # Siempre se verifica un hash (aunque el usuario no exista) para no filtrar emails por timing.
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.is_active:
        login_limiter.hit(key)
        raise UnauthorizedError("Email o contraseña incorrectos", code="invalid_credentials")

    login_limiter.reset(key)
    settings = get_settings()
    response.set_cookie(
        settings.cookie_name,
        create_access_token(user.id, user.role),
        max_age=settings.jwt_expires_minutes * 60,
        httponly=True,  # inaccesible desde JS: mitiga robo de sesión por XSS
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )
    return UserOut.model_validate(user)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(get_settings().cookie_name, path="/")


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
