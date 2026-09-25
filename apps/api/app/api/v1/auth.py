from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.db import SessionDep
from app.core.errors import ForbiddenError, TooManyRequestsError, UnauthorizedError
from app.core.rate_limit import login_ip_limiter, login_limiter
from app.core.security import DUMMY_HASH, create_access_token, verify_password
from app.models import User
from app.schemas.auth import LoginIn, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# Fecha de la versión vigente de /terminos y /privacidad: si cambia, se vuelve a pedir aceptación.
TERMS_VERSION = "2026-09-24"


@router.post("/login")
async def login(
    body: LoginIn, request: Request, response: Response, session: SessionDep
) -> UserOut:
    email = body.email.lower()
    ip = request.client.host if request.client else "-"
    key = f"{ip}:{email}"
    if login_limiter.is_blocked(key) or login_ip_limiter.is_blocked(ip):
        raise TooManyRequestsError(
            "Demasiados intentos. Espera unos minutos e inténtalo de nuevo",
            code="too_many_attempts",
        )

    user = await session.scalar(select(User).where(func.lower(User.email) == email))
    # Siempre se verifica un hash (aunque el usuario no exista) para no filtrar emails por timing.
    # bcrypt tarda ~200 ms de CPU: en un hilo, para no congelar el event loop (y con él a
    # todos los estudiantes conectados a este worker) en cada login.
    valid = await run_in_threadpool(
        verify_password, body.password, user.password_hash if user else DUMMY_HASH
    )
    if not user or not valid or not user.is_active:
        login_limiter.hit(key)
        login_ip_limiter.hit(ip)
        raise UnauthorizedError("Email o contraseña incorrectos", code="invalid_credentials")

    login_limiter.reset(key)
    if user.terms_version != TERMS_VERSION:
        # Solo tras validar la contraseña: no revela a un extraño si la cuenta existe.
        if not body.accept_terms:
            raise ForbiddenError(
                "Acepta los Términos y la Política de privacidad para continuar",
                code="terms_required",
            )
        user.terms_version = TERMS_VERSION
        user.terms_accepted_at = datetime.now(UTC)
        await session.commit()
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
