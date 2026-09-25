import uuid

from fastapi import APIRouter, Request, Response

from app.api.deps import CurrentUser, PaidUser
from app.core.db import SessionDep
from app.core.errors import AppError, NotFoundError
from app.schemas.attempt import (
    AnswerIn,
    AnswerSavedOut,
    AssessmentSummaryOut,
    AttemptOut,
    AttemptResultOut,
    FeedbackOut,
    IntegrityEventsIn,
    SpeechSavedOut,
    SubmitIn,
)
from app.services import attempt_service, coach_ai

router = APIRouter(tags=["assessments"])

# ~60 s de voz en opus/aac pesan < 1 MB; el margen cubre navegadores con bitrate alto.
MAX_SPEECH_BYTES = 5 * 1024 * 1024


async def read_audio(request: Request) -> tuple[bytes, str]:
    """Cuerpo crudo de audio (audio/webm, audio/mp4, audio/ogg...) y su tipo."""
    content_type = request.headers.get("content-type", "").split(";")[0].strip()
    if not content_type.startswith("audio/"):
        raise AppError("Envía la grabación como audio", code="invalid_audio")
    # Se corta leyendo por partes: con Transfer-Encoding: chunked no hay Content-Length y
    # `request.body()` cargaría en memoria lo que el cliente quiera mandar.
    audio = bytearray()
    async for chunk in request.stream():
        audio += chunk
        if len(audio) > MAX_SPEECH_BYTES:
            raise AppError("La grabación es demasiado larga", code="audio_too_large")
    if not audio:
        raise AppError("La grabación está vacía", code="invalid_audio")
    return bytes(audio), content_type


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


@router.put("/attempts/{attempt_id}/answers/{question_id}/speech")
async def save_speech(
    attempt_id: uuid.UUID,
    question_id: uuid.UUID,
    request: Request,
    user: PaidUser,
    session: SessionDep,
) -> SpeechSavedOut:
    """Respuesta oral: el cuerpo es el audio crudo (audio/webm, audio/mp4, audio/ogg...)."""
    audio, content_type = await read_audio(request)
    return await attempt_service.save_speech(
        session, user, attempt_id, question_id, audio, content_type
    )


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
async def coach_feedback(attempt_id: uuid.UUID, user: PaidUser, session: SessionDep) -> FeedbackOut:
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
    attempt_id: uuid.UUID, user: PaidUser, session: SessionDep
) -> Response:
    attempt = await attempt_service.get_attempt(session, user, attempt_id)
    audio = attempt.ai_feedback and await coach_ai.synthesize(str(attempt.id), attempt.ai_feedback)
    return _mp3(audio)


@router.get("/attempts/{attempt_id}/recommendation/audio", response_class=Response)
async def recommendation_audio(
    attempt_id: uuid.UUID, user: PaidUser, session: SessionDep
) -> Response:
    """Glo presenta el curso recomendado: audio aparte para poder oírlo desde su inicio."""
    data = await attempt_service.get_result(session, user, attempt_id)  # 409 si sigue abierto
    return _mp3(await coach_ai.synthesize(f"{data.id}:rec", data.result.recommendation.script))


def _mp3(audio: bytes | None) -> Response:
    if not audio:
        raise NotFoundError("La voz del coach no está disponible", code="tts_unavailable")
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "private, no-cache"})
