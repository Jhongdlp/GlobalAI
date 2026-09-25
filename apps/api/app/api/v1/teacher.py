"""Rutas de profesor/admin. El rol se exige una vez, a nivel de router: ninguna ruta nueva
aquí puede quedar abierta a estudiantes por olvido."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_roles
from app.core.db import SessionDep
from app.models import Role
from app.schemas.progress import (
    TeacherAttemptDetailOut,
    TeacherAttemptOut,
    TeacherOverviewOut,
    TeacherStudentDetailOut,
)
from app.services import progress_service, teacher_service

router = APIRouter(
    prefix="/teacher",
    tags=["teacher"],
    dependencies=[Depends(require_roles(Role.TEACHER, Role.ADMIN))],
)


@router.get("/overview")
async def overview(session: SessionDep) -> TeacherOverviewOut:
    """Panorama del grupo: indicadores, niveles, habilidades, estudiantes y alertas."""
    return await teacher_service.overview(session)


@router.get("/attempts")
async def recent_attempts(
    session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> list[TeacherAttemptOut]:
    """Intentos recientes con banderas de integridad."""
    return await progress_service.list_recent_attempts(session, limit)


@router.get("/attempts/{attempt_id}")
async def attempt_detail(attempt_id: uuid.UUID, session: SessionDep) -> TeacherAttemptDetailOut:
    """Resultado, respuestas y bitácora de integridad de cualquier intento enviado."""
    return await teacher_service.attempt_detail(session, attempt_id)


@router.get("/students/{student_id}")
async def student_detail(student_id: uuid.UUID, session: SessionDep) -> TeacherStudentDetailOut:
    return await teacher_service.student_detail(session, student_id)
