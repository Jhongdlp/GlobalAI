import base64
import hashlib
import random

from fastapi import APIRouter, Request, Response

from app.api.deps import CurrentUser, PaidUser
from app.api.v1.assessments import _mp3, read_audio
from app.core.errors import AppError, NotFoundError, ServiceUnavailableError
from app.domain.practice import LESSONS, MAX_TURNS, clips, said_right, unclear_words
from app.domain.speaking import words_from_stt
from app.schemas.practice import HeardOut, LessonOut, ReplyIn, ReplyOut
from app.services import coach_ai, speech

router = APIRouter(prefix="/practice", tags=["practice"])


def _lesson(lesson_id: str):
    if lesson_id not in LESSONS:
        raise NotFoundError("Clase no encontrada")
    return LESSONS[lesson_id]


@router.get("/lesson")
async def lesson(_: CurrentUser, exclude: str | None = None) -> LessonOut:
    """Una clase al azar (distinta de `exclude`, para "otra clase")."""
    pick = random.choice([x for x in LESSONS.values() if x.id != exclude])
    return LessonOut(
        **{k: getattr(pick, k) for k in ("id", "sound", "word", "tip", "question")},
        max_turns=MAX_TURNS,
    )


@router.get("/{lesson_id}/audio/{clip}", response_class=Response)
async def lesson_audio(lesson_id: str, clip: str, _: CurrentUser) -> Response:
    """Frases fijas de Glo. Sin PaidUser: el texto no lo elige el cliente y queda en caché."""
    text = clips(_lesson(lesson_id)).get(clip)
    if not text:
        raise NotFoundError("Audio no disponible")
    return _mp3(await coach_ai.synthesize(f"practice:{lesson_id}:{clip}", text))


@router.post("/listen")
async def listen(request: Request, _: PaidUser, lesson: str | None = None) -> HeardOut:
    """Transcribe al estudiante; con `lesson`, dice si pronunció bien la palabra de la clase."""
    audio, content_type = await read_audio(request)
    stt = await speech.transcribe(audio, content_type)
    if stt is None:
        raise ServiceUnavailableError(
            "La práctica oral no está disponible ahora", code="stt_unavailable"
        )
    words = words_from_stt(stt)
    if not words:
        raise AppError("No logramos escucharte. Habla un poco más fuerte.", code="no_speech")
    ok = said_right(_lesson(lesson).word, words) if lesson else None
    return HeardOut(text=(stt.get("text") or "").strip(), ok=ok, unclear=unclear_words(words))


@router.post("/reply")
async def reply(body: ReplyIn, _: PaidUser) -> ReplyOut:
    done = len(body.turns) >= 2 * MAX_TURNS
    out = await speech.chat_reply(body.turns, closing=done)
    # En voz: primero la corrección (para imitarla), luego la charla sigue.
    said = f"You can say: {out['fix']} ... {out['reply']}" if out["fix"] else out["reply"]
    audio = await coach_ai.synthesize("practice:" + hashlib.sha256(said.encode()).hexdigest(), said)
    return ReplyOut(
        text=out["reply"],
        fix=out["fix"],
        why=out["why"],
        audio=audio and base64.b64encode(audio).decode(),
        done=done,
    )
