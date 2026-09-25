"""Reglas de calificación. Funciones puras: sin base de datos ni FastAPI, fáciles de testear."""

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

# Umbrales para sugerir nivel (ver suggest_level).
LEVEL_OWN_THRESHOLD = 0.5
LEVEL_CUMULATIVE_THRESHOLD = 0.6
# Speaking da crédito parcial (0-1); cuenta como "correcta" desde este puntaje.
SPEECH_PASS_THRESHOLD = 0.6


def normalize_text(value: str) -> str:
    """Normaliza respuestas escritas: minúsculas, espacios colapsados, sin puntuación final
    y apóstrofos tipográficos unificados ("Don’t." == "don't")."""
    value = unicodedata.normalize("NFKC", value).replace("’", "'").replace("‘", "'")
    value = re.sub(r"\s+", " ", value.strip().lower())
    return value.rstrip(".!?,;:")


def is_correct(
    response_format: str, answer_key: Mapping[str, Any], response: Mapping[str, Any]
) -> bool:
    if response_format == "choice":
        return response.get("option_id") == answer_key["option_id"]
    if response_format == "text":
        given = normalize_text(str(response.get("text", "")))
        return bool(given) and given in {normalize_text(a) for a in answer_key["accepted"]}
    raise ValueError(f"Formato de respuesta desconocido: {response_format}")


def credit(
    response_format: str, answer_key: Mapping[str, Any], response: Mapping[str, Any]
) -> float:
    """Fracción del puntaje ganada. Speaking ya viene calificado por el servidor al grabar."""
    if response_format == "speech":
        return max(0.0, min(1.0, float(response.get("score", 0))))
    return float(is_correct(response_format, answer_key, response))


@dataclass(frozen=True)
class GradableItem:
    question_id: str
    skill_code: str
    level_code: str
    response_format: str
    answer_key: Mapping[str, Any]
    response: Mapping[str, Any] | None  # None = sin responder
    points: int = 1


@dataclass
class Tally:
    correct: int = 0
    total: int = 0
    points: float = 0
    max_points: int = 0

    @property
    def pct(self) -> float:
        return round(100 * self.points / self.max_points, 2) if self.max_points else 0.0

    @property
    def ratio(self) -> float:
        return self.points / self.max_points if self.max_points else 0.0


@dataclass
class GradeResult:
    score_pct: float
    correct_count: int
    incorrect_count: int
    unanswered_count: int
    by_skill: dict[str, Tally]
    by_level: dict[str, Tally]
    per_question: dict[str, bool] = field(default_factory=dict)


def grade(items: Iterable[GradableItem]) -> GradeResult:
    overall = Tally()
    by_skill: dict[str, Tally] = defaultdict(Tally)
    by_level: dict[str, Tally] = defaultdict(Tally)
    per_question: dict[str, bool] = {}
    unanswered = 0

    for item in items:
        earned = (
            credit(item.response_format, item.answer_key, item.response)
            if item.response is not None
            else 0.0
        )
        ok = earned >= (SPEECH_PASS_THRESHOLD if item.response_format == "speech" else 1)
        unanswered += item.response is None
        per_question[item.question_id] = ok
        for tally in (overall, by_skill[item.skill_code], by_level[item.level_code]):
            tally.total += 1
            tally.max_points += item.points
            tally.points += item.points * earned
            tally.correct += ok

    return GradeResult(
        score_pct=overall.pct,
        correct_count=overall.correct,
        # Las no respondidas cuentan como incorrectas en el conteo que ve el estudiante.
        incorrect_count=overall.total - overall.correct,
        unanswered_count=unanswered,
        by_skill=dict(by_skill),
        by_level=dict(by_level),
        per_question=per_question,
    )


def suggest_level(by_level: Mapping[str, Tally], level_ranks: Mapping[str, int]) -> str:
    """Nivel MCER sugerido.

    Recorre los niveles evaluados de menor a mayor. Un nivel se "alcanza" si el estudiante
    acierta al menos 50% de las preguntas de ese nivel y 60% acumulado de todo lo que está en
    ese nivel o por debajo. El acumulado evita que un error aislado en A1 hunda a alguien que
    domina B1, y el umbral propio evita "saltar" niveles por acumulado.
    Si no alcanza ninguno, se sugiere el nivel inmediatamente inferior al más bajo evaluado.
    """
    tested = sorted((code for code in by_level if code in level_ranks), key=level_ranks.__getitem__)
    if not tested:
        raise ValueError("No hay niveles evaluados")

    points = max_points = 0
    suggested: str | None = None
    for code in tested:
        tally = by_level[code]
        points += tally.points
        max_points += tally.max_points
        if tally.ratio >= LEVEL_OWN_THRESHOLD and points / max_points >= LEVEL_CUMULATIVE_THRESHOLD:
            suggested = code

    if suggested:
        return suggested
    lowest_rank = level_ranks[tested[0]]
    below = [c for c, r in level_ranks.items() if r < lowest_rank]
    return max(below, key=level_ranks.__getitem__) if below else tested[0]
