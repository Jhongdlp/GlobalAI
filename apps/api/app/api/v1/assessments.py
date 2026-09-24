import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.schemas.attempt import (
    AnswerIn,
    AnswerSavedOut,
    AssessmentSummaryOut,
    AttemptOut,
    AttemptResultOut,
    IntegrityEventsIn,
    SubmitIn,
)
from app.services import attempt_service

router = APIRouter(tags=["assessments"])


@router.get("/assessments")
async def list_assessments(user: CurrentUser, session: SessionDep) -> list[AssessmentSummaryOut]:
    return await attempt_service.list_assessments(session, user)


@router.post("/assessments/{slug}/attempts")
async def start_attempt(slug: str, user: CurrentUser, session: SessionDep) -> AttemptOut:
    """Inicia un intento o reanuda el que esté abierto (idempotente)."""
    attempt = await attempt_service.start_or_resume(session, user, slug)
    return await attempt_service.build_attempt_view(session, attempt)


@router.get("/attempts/{attempt_id}")
async def get_attempt(attempt_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> AttemptOut:
    attempt = await attempt_service.get_attempt(session, user, attempt_id)
    return await attempt_service.build_attempt_view(session, attempt)


@router.put("/attempts/{attempt_id}/answers/{question_id}")
async def save_answer(
    attempt_id: uuid.UUID,
    question_id: uuid.UUID,
    body: AnswerIn,
    user: CurrentUser,
    session: SessionDep,
) -> AnswerSavedOut:
    """Autoguardado de una respuesta. PUT idempotente: reintentar tras un corte es seguro."""
    saved_at = await attempt_service.save_answer(session, user, attempt_id, question_id, body)
    return AnswerSavedOut(question_id=question_id, saved_at=saved_at)


@router.post("/attempts/{attempt_id}/events", status_code=202)
async def record_events(
    attempt_id: uuid.UUID, body: IntegrityEventsIn, user: CurrentUser, session: SessionDep
) -> dict[str, int]:
    flags = await attempt_service.record_events(session, user, attempt_id, body)
    return {"integrity_flags": flags}


@router.post("/attempts/{attempt_id}/submit")
async def submit_attempt(
    attempt_id: uuid.UUID, body: SubmitIn, user: CurrentUser, session: SessionDep
) -> AttemptResultOut:
    await attempt_service.submit(session, user, attempt_id, body)
    return await attempt_service.get_result(session, user, attempt_id)


@router.get("/attempts/{attempt_id}/result")
async def get_result(
    attempt_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> AttemptResultOut:
    return await attempt_service.get_result(session, user, attempt_id)
