import uuid

from fastapi import APIRouter, Response

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.core.errors import NotFoundError
from app.schemas.attempt import (
    AnswerIn,
    AnswerSavedOut,
    AssessmentSummaryOut,
    AttemptOut,
    AttemptResultOut,
    FeedbackOut,
    IntegrityEventsIn,
    SubmitIn,
)
from app.services import attempt_service, coach_ai

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


@router.post("/attempts/{attempt_id}/feedback")
async def coach_feedback(
    attempt_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> FeedbackOut:
    """Feedback del English Coach. Se genera una sola vez por intento y queda guardado:
    el costo de IA está acotado y el estudiante ve siempre el mismo texto."""
    data = await attempt_service.get_result(session, user, attempt_id)  # 409 si sigue abierto
    if data.result.ai_feedback:
        return FeedbackOut(feedback=data.result.ai_feedback)
    # ponytail: la llamada al LLM retiene la conexión a BD; a escala, moverlo a una cola.
    text = await coach_ai.generate_feedback(data)
    attempt = await attempt_service.get_attempt(session, user, attempt_id)
    attempt.ai_feedback = text
    await session.commit()
    return FeedbackOut(feedback=text)


@router.get("/attempts/{attempt_id}/feedback/audio", response_class=Response)
async def coach_feedback_audio(
    attempt_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    attempt = await attempt_service.get_attempt(session, user, attempt_id)
    audio = attempt.ai_feedback and await coach_ai.synthesize(str(attempt.id), attempt.ai_feedback)
    if not audio:
        raise NotFoundError("La voz del coach no está disponible", code="tts_unavailable")
    return Response(
        audio, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"}
    )
