import uuid
from typing import Annotated

import jwt
from fastapi import Depends, Request

from app.core.config import get_settings
from app.core.db import SessionDep
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.rate_limit import api_limiter, paid_limiter
from app.core.security import decode_access_token
from app.models import Role, User


def _token_from_request(request: Request) -> str | None:
    # Cookie httpOnly para el navegador; Bearer para Swagger, apps móviles o integraciones.
    token = request.cookies.get(get_settings().cookie_name)
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    return auth.removeprefix("Bearer ").strip() or None


async def get_current_user(request: Request, session: SessionDep) -> User:
    token = _token_from_request(request)
    if not token:
        raise UnauthorizedError("Inicia sesión para continuar")
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise UnauthorizedError("Tu sesión expiró, vuelve a iniciar sesión") from exc

    # Toda ruta autenticada pasa por aquí: un solo punto para el límite por usuario.
    api_limiter.consume(str(user_id))
    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("Usuario no válido")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def paid_call(user: CurrentUser) -> User:
    """Para rutas que gastan créditos de un proveedor externo (STT, LLM, TTS)."""
    paid_limiter.consume(str(user.id))
    return user


PaidUser = Annotated[User, Depends(paid_call)]


def require_roles(*roles: Role):
    """Dependencia de autorización: `Depends(require_roles(Role.TEACHER, Role.ADMIN))`."""

    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise ForbiddenError("No tienes permisos para este recurso")
        return user

    return checker
