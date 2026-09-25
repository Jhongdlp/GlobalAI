"""Calificación de Speaking a partir de la transcripción de ElevenLabs Scribe. Funciones puras.

Scribe no evalúa pronunciación; lo que sí entrega (texto, tiempos y confianza por palabra)
alcanza para medir cuatro cosas defendibles:
- precisión: qué parte del texto objetivo se entendió (lectura en voz alta),
- contenido: tarea, gramática y vocabulario según una rúbrica que aplica el LLM (respuesta libre),
- claridad: confianza media del reconocedor; si la máquina dudó, a un oyente le costaría,
- fluidez: palabras por minuto y pausas largas.

La entrega (claridad y fluidez) modula el contenido y no lo sustituye: leer otra cosa con
fluidez o hablar fuera de tema vale ~0.
"""

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

LONG_PAUSE_S = 1.0
NATURAL_WPM = 110  # ritmo cómodo de un hablante no nativo competente
RUBRIC_KEYS = ("task", "grammar", "vocabulary")  # 0-4 cada uno
# Sin LLM, la respuesta libre solo puede medir cuánto se habló: techo bajo a propósito.
HEURISTIC_CONTENT_CAP = 0.75


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float
    logprob: float


def words_from_stt(payload: Mapping[str, Any]) -> list[Word]:
    return [
        Word(w["text"], w.get("start") or 0.0, w.get("end") or 0.0, w.get("logprob") or 0.0)
        for w in payload.get("words") or []
        if w.get("type") == "word"
    ]


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))


def clarity(words: list[Word]) -> float:
    return sum(min(1.0, math.exp(w.logprob)) for w in words) / len(words) if words else 0.0


def fluency(words: list[Word]) -> tuple[float, float, int]:
    """(puntaje 0-1, palabras por minuto, pausas largas)."""
    if len(words) < 2:
        return 0.0, 0.0, 0
    duration = words[-1].end - words[0].start
    if duration <= 0:
        return 0.0, 0.0, 0
    wpm = len(words) * 60 / duration
    pauses = sum(b.start - a.end > LONG_PAUSE_S for a, b in zip(words, words[1:], strict=False))
    return max(0.0, min(1.0, wpm / NATURAL_WPM) - 0.1 * pauses), round(wpm), pauses


def _combine(content: float, words: list[Word]) -> dict[str, Any]:
    clear = clarity(words)
    fluent, wpm, pauses = fluency(words)
    return {
        "score": round(content * (0.6 + 0.2 * clear + 0.2 * fluent), 3),
        "clarity": round(clear, 3),
        "fluency": round(fluent, 3),
        "wpm": wpm,
        "long_pauses": pauses,
    }


def score_read_aloud(target: str, words: list[Word]) -> dict[str, Any]:
    expected = tokens(target)
    spoken = [t for w in words for t in tokens(w.text)]
    blocks = SequenceMatcher(None, expected, spoken, autojunk=False).get_matching_blocks()
    hit = {i for b in blocks for i in range(b.a, b.a + b.size)}
    accuracy = len(hit) / len(expected) if expected else 0.0
    return {
        **_combine(accuracy, words),
        "accuracy": round(accuracy, 3),
        "missed": [t for i, t in enumerate(expected) if i not in hit],
    }


def parse_rubric(text: str) -> dict[str, Any] | None:
    """Extrae el JSON de la rúbrica de la respuesta del LLM; None si no es válido."""
    match = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(match.group(0)) if match else None
        rubric = {k: max(0, min(4, int(data[k]))) for k in RUBRIC_KEYS}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    feedback = data.get("feedback")
    return rubric | {"feedback": str(feedback)[:300] if feedback else None}


def score_open_response(
    words: list[Word], rubric: Mapping[str, Any] | None, min_words: int
) -> dict[str, Any]:
    if rubric:
        content = sum(rubric[k] for k in RUBRIC_KEYS) / (4 * len(RUBRIC_KEYS))
        return {
            **_combine(content, words),
            "rubric": {k: rubric[k] for k in RUBRIC_KEYS},
            "feedback": rubric.get("feedback"),
            "graded_by": "ai",
        }
    content = HEURISTIC_CONTENT_CAP * min(1.0, len(words) / min_words)
    return {**_combine(content, words), "feedback": None, "graded_by": "heuristic"}
