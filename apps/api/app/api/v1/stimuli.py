import uuid
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import array

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.core.errors import NotFoundError
from app.models import Attempt, Question, Stimulus
from app.models.assessment import StimulusKind

router = APIRouter(tags=["assessments"])

# Audios pregenerados (TTS) versionados junto al código, uno por `stimulus.code`.
# ponytail: archivos locales; en producción irían a S3/R2 con URL firmada de corta duración.
AUDIO_DIR = Path(__file__).resolve().parents[2] / "assets" / "audio"


@router.get("/stimuli/{stimulus_id}/audio", response_class=FileResponse)
async def stimulus_audio(
    stimulus_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> FileResponse:
    """Sirve el audio de un Listening. La transcripción nunca sale al cliente antes del envío.

    Solo a quien tiene un intento que incluye una pregunta con este audio: un ID adivinado
    (o de una evaluación no publicada) da 404, igual que si no existiera."""
    question_ids = [
        str(q)
        for q in await session.scalars(
            select(Question.id).where(Question.stimulus_id == stimulus_id)
        )
    ]
    allowed = question_ids and await session.scalar(
        select(
            exists().where(
                Attempt.user_id == user.id,
                Attempt.layout["questions"].has_any(array(question_ids)),
            )
        )
    )
    stimulus = await session.get(Stimulus, stimulus_id) if allowed else None
    path = AUDIO_DIR / f"{stimulus.code}.mp3" if stimulus else None
    if not stimulus or stimulus.kind != StimulusKind.AUDIO or not path or not path.is_file():
        raise NotFoundError("Audio no disponible")
    # no-cache: el navegador revalida por ETag (304 si no cambió); un mp3 regenerado se oye ya.
    return FileResponse(
        path, media_type="audio/mpeg", headers={"Cache-Control": "private, no-cache"}
    )
