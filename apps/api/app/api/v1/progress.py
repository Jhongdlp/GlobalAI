from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, require_roles
from app.core.db import SessionDep
from app.models import Role, User
from app.schemas.progress import ProgressOut, TeacherAttemptOut
from app.services import progress_service

router = APIRouter(tags=["progress"])


@router.get("/me/progress")
async def my_progress(user: CurrentUser, session: SessionDep) -> ProgressOut:
    return await progress_service.get_progress(session, user)


@router.get("/teacher/attempts")
async def recent_attempts(
    _: Annotated[User, Depends(require_roles(Role.TEACHER, Role.ADMIN))],
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[TeacherAttemptOut]:
    """Vista de profesor/admin: intentos recientes con banderas de integridad."""
    return await progress_service.list_recent_attempts(session, limit)
