"""Curso recomendado tras la evaluación: el puente entre el resultado y la matrícula.

Determinista a propósito: el LLM redacta el feedback, pero nunca decide qué curso se vende.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Course:
    title: str
    weeks: int
    promise: str  # completa la frase "N semanas para ..."


# ponytail: catálogo en código; pasarlo a una tabla `courses` cuando lo edite el equipo académico.
COURSES = {
    "PRE_A1": Course("English Starter", 8, "presentarte y entender frases del día a día"),
    "A1": Course("English Foundations", 10, "conversar sobre ti, tu rutina y tu entorno"),
    "A2": Course("Everyday English", 10, "desenvolverte en viajes, compras y el trabajo"),
    "B1": Course("Confident Communicator", 12, "opinar, contar experiencias y hablar con fluidez"),
    "B2": Course("Professional English", 12, "reuniones, presentaciones y correos de trabajo"),
    "C1": Course("C1 Mastery & Certification", 10, "pulir tu inglés y certificar tu nivel C1"),
}

FOCUS_BELOW = 80  # habilidades bajo este % entran como foco del curso


def focus_skills(skills: Sequence[tuple[str, float]], limit: int = 2) -> list[str]:
    """Las habilidades más débiles (nombre, %), de menor a mayor."""
    weak = sorted((s for s in skills if s[1] < FOCUS_BELOW), key=lambda s: s[1])
    return [name for name, _ in weak[:limit]]


def script(course: Course, level: str, focus: list[str]) -> str:
    """Lo que Glo dice en voz alta (español, frases cortas: se lee con TTS y se subtitula)."""
    if len(focus) == 2:
        why = f"Pondremos foco en {focus[0]} y {focus[1]}, que es donde más vas a crecer."
    elif focus:
        why = f"Pondremos foco en {focus[0]}, que es donde más vas a crecer."
    else:
        why = "Vas parejo en todas las habilidades, así que avanzaremos en todas a la vez."
    return (
        f"Y ahora, tu siguiente paso. Te recomiendo el curso {course.title}, nivel {level}. "
        f"Son {course.weeks} semanas para {course.promise}. {why} ¿Empezamos?"
    )


def recommend(level_code: str, skills: Sequence[tuple[str, float]]) -> dict:
    """Curso del nivel + foco en las habilidades más débiles, listo para RecommendationOut."""
    course = COURSES[level_code]
    level = level_code.replace("PRE_", "Pre-")
    focus = focus_skills(skills)
    return {
        "course": course.title,
        "level": level,
        "weeks": course.weeks,
        "promise": course.promise,
        "focus": focus,
        "script": script(course, level, focus),
    }


if __name__ == "__main__":
    scores = [("Grammar", 90), ("Reading", 50), ("Listening", 20), ("Vocabulary", 70)]
    assert focus_skills(scores) == ["Listening", "Reading"]
    assert focus_skills([("Grammar", 100)]) == []
    assert set(COURSES) == {"PRE_A1", "A1", "A2", "B1", "B2", "C1"}
    assert "Listening y Reading" in script(COURSES["B1"], "B1", ["Listening", "Reading"])
    assert recommend("PRE_A1", scores)["level"] == "Pre-A1"
    print("ok")
