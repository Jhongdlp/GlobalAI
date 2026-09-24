"""English Coach: feedback educativo con IA, desacoplado del proveedor.

El resto del sistema solo conoce `generate_feedback()` y `synthesize()`. Cambiar OpenAI por
Claude (u otro modelo) = una clase con `complete()` + `AI_PROVIDER` en el entorno.
Si el proveedor falla o no hay key, se usa un feedback por plantilla: el estudiante
siempre recibe una respuesta y la IA nunca bloquea la entrega de resultados.

Privacidad: al modelo solo viajan puntajes y preguntas falladas, nunca nombre ni email.
"""

import logging
from collections import OrderedDict
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.schemas.attempt import AttemptResultOut

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Eres Glo, coach de inglés de Global AI. Escribes feedback breve para un estudiante "
    "hispanohablante que acaba de terminar una evaluación de nivel. Tono cálido, directo y "
    "adulto (sin infantilizar). Escribe en español; las palabras o ejemplos en inglés van "
    "entre comillas. Máximo 110 palabras, 3 párrafos cortos, texto plano sin markdown, "
    "sin listas ni emojis (el texto también se lee en voz alta). Párrafo 1: interpreta el "
    "nivel y el puntaje. Párrafo 2: explica el error más importante con un ejemplo correcto. "
    "Párrafo 3: un siguiente paso concreto para practicar esta semana."
)


class CoachProvider(Protocol):
    async def complete(self, system: str, prompt: str) -> str: ...


class OpenAIProvider:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def complete(self, system: str, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0.6,
                    "max_tokens": 400,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()


def get_provider() -> CoachProvider | None:
    settings = get_settings()
    if settings.ai_provider == "openai" and settings.openai_api_key:
        return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    return None


def _level(code: str) -> str:
    return code.replace("PRE_", "Pre-")  # PRE_A1 -> Pre-A1 para humanos y para el modelo


def _answer_text(item) -> str:
    response = item.response or {}
    if "text" in response:
        return response["text"] or "(vacío)"
    options = {o.id: o.text for o in item.question.options or []}
    return options.get(response.get("option_id"), "(sin responder)")


def build_prompt(data: AttemptResultOut) -> str:
    r = data.result
    skills = ", ".join(f"{s.name} {s.pct:.0f}%" for s in r.skills)
    mistakes = "\n".join(
        f'- [{i.question.skill}, {i.question.level}] "{i.question.prompt}" · respondió: '
        f'"{_answer_text(i)}" · correcta: "{i.correct_answer}"'
        for i in data.review
        if not i.is_correct
    )
    return (
        f"Evaluación: {data.assessment_title}\n"
        f"Puntaje global: {r.score_pct:.0f}% ({r.correct_count} de "
        f"{r.correct_count + r.incorrect_count} correctas)\n"
        f"Nivel sugerido: {_level(r.suggested_level.code)} ({r.suggested_level.name})\n"
        f"Por habilidad: {skills}\n"
        f"Errores:\n{mistakes or '- Ninguno'}"
    )


def template_feedback(data: AttemptResultOut) -> str:
    """Respaldo determinista (sin proveedor o si el proveedor falla)."""
    r = data.result
    ordered = sorted(r.skills, key=lambda s: s.pct)
    weak, strong = ordered[0], ordered[-1]
    return (
        f"Obtuviste {r.score_pct:.0f}% y tu nivel sugerido es {_level(r.suggested_level.code)} "
        f"({r.suggested_level.name}). Tu punto más fuerte es {strong.name} con "
        f"{strong.pct:.0f}%.\n\n"
        f"Donde más puedes crecer es {weak.name} ({weak.pct:.0f}%). Revisa las respuestas "
        f"de abajo: cada una trae la explicación de la opción correcta.\n\n"
        f"Esta semana dedica 15 minutos diarios a {weak.name} y vuelve a presentar la "
        f"evaluación para medir tu avance."
    )


async def generate_feedback(data: AttemptResultOut) -> str:
    provider = get_provider()
    if provider:
        try:
            return await provider.complete(SYSTEM_PROMPT, build_prompt(data))
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            log.warning("AI feedback provider failed, using template: %s", exc)
    return template_feedback(data)


# ---------------------------------------------------------------------------
# Voz (TTS)
# ---------------------------------------------------------------------------

# ponytail: caché en memoria por proceso; con varias réplicas, guardar el mp3 en S3/R2.
_audio_cache: OrderedDict[str, bytes] = OrderedDict()
_AUDIO_CACHE_SIZE = 50
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # voz prediseñada de ElevenLabs, soporta español


async def synthesize(key: str, text: str) -> bytes | None:
    """Audio mp3 del texto con ElevenLabs, o None si la voz no está configurada o falla."""
    settings = get_settings()
    if settings.tts_provider != "elevenlabs" or not settings.elevenlabs_api_key:
        return None
    voice = settings.elevenlabs_voice_id or DEFAULT_VOICE_ID
    if key in _audio_cache:
        _audio_cache.move_to_end(key)
        return _audio_cache[key]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                params={"output_format": "mp3_44100_128"},
                headers={"xi-api-key": settings.elevenlabs_api_key},
                json={"text": text, "model_id": "eleven_multilingual_v2"},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("TTS provider failed: %s", exc)
        return None
    _audio_cache[key] = response.content
    if len(_audio_cache) > _AUDIO_CACHE_SIZE:
        _audio_cache.popitem(last=False)
    return response.content
