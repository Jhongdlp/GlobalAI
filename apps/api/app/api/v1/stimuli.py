import uuid
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser
from app.core.db import SessionDep
from app.core.errors import NotFoundError
from app.models import Stimulus
from app.models.assessment import StimulusKind

router = APIRouter(tags=["assessments"])

# Audios pregenerados (TTS) versionados junto al código, uno por `stimulus.code`.
# ponytail: archivos locales; en producción irían a S3/R2 con URL firmada de corta duración.
AUDIO_DIR = Path(__file__).resolve().parents[2] / "assets" / "audio"


@router.get("/stimuli/{stimulus_id}/audio", response_class=FileResponse)
async def stimulus_audio(
    stimulus_id: uuid.UUID, _: CurrentUser, session: SessionDep
) -> FileResponse:
    """Sirve el audio de un Listening. La transcripción nunca sale al cliente antes del envío."""
    stimulus = await session.get(Stimulus, stimulus_id)
    path = AUDIO_DIR / f"{stimulus.code}.mp3" if stimulus else None
    if not stimulus or stimulus.kind != StimulusKind.AUDIO or not path or not path.is_file():
        raise NotFoundError("Audio no disponible")
    return FileResponse(
        path, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"}
    )
