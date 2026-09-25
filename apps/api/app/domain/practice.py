"""Mini clase de pronunciación con Glo: un sonido, una palabra y una charla corta. Funciones puras.

Lo fijo (explicación, "muy bien", "otra vez", la pregunta) se sintetiza una vez y queda en caché:
por estudiante solo se paga la transcripción de lo que dice y, en la charla, respuestas muy cortas.
"""

import math
from dataclasses import dataclass

from app.domain.speaking import Word, clarity, tokens

# ponytail: umbral a ojo con Scribe; calibrar con grabaciones reales de estudiantes.
CLARITY_OK = 0.6
UNCLEAR_WORD = 0.5  # confianza por palabra bajo la cual la marcamos para repetir
MAX_TURNS = 2  # respuestas del estudiante en la charla: acota tokens y la sesión dura ~1 min


@dataclass(frozen=True)
class Lesson:
    id: str
    sound: str
    word: str
    tip: str  # en pantalla
    intro: str  # lo que Glo dice (voz)
    question: str


LESSONS = {
    lesson.id: lesson
    for lesson in (
        Lesson(
            "th",
            "th",
            "think",
            "Pon la punta de la lengua entre los dientes y sopla suave. No es «t» ni «s».",
            "Mini clase: el sonido th. Pon la punta de la lengua entre los dientes y sopla "
            "suave, sin decir t ni s. Escucha cómo se dice.",
            "What do you usually think about in the morning?",
        ),
        Lesson(
            "v",
            "v",
            "very",
            "Apoya los dientes de arriba en el labio de abajo y deja que vibre. No es «b».",
            "Mini clase: el sonido v. Apoya los dientes de arriba en el labio de abajo y deja "
            "que vibre. Escucha cómo se dice.",
            "What is your favorite movie?",
        ),
        Lesson(
            "i",
            "i corta",
            "ship",
            "Una «i» corta y relajada, casi entre «i» y «e». «Sheep» es larga; «ship», corta.",
            "Mini clase: la i corta. Es relajada y rápida, casi entre i y e, nunca una i larga. "
            "Escucha cómo se dice.",
            "What did you do this weekend?",
        ),
    )
}


def clips(lesson: Lesson) -> dict[str, str]:
    """Frases fijas de Glo para esta clase (cada una se sintetiza una sola vez).

    La palabra modelo va en su propio clip: metida en una frase en español, la voz la dice
    con acento ("think" suena "pink"); sola, la pronuncia en inglés."""
    return {
        "intro": lesson.intro,
        "word": f"{lesson.word}... {lesson.word}.",
        "good": "¡Muy bien! Así se dice.",
        "again": "Casi. Escúchala otra vez y fíjate en el sonido.",
        "question": f"Now, let's talk! {lesson.question}",
    }


def unclear_words(words: list[Word]) -> list[str]:
    """Palabras que el reconocedor dudó: a un oyente también le costarían."""
    return [w.text for w in words if math.exp(w.logprob) < UNCLEAR_WORD]


def said_right(word: str, words: list[Word]) -> bool:
    """La palabra se entendió tal cual y sin que el reconocedor dudara."""
    return word in {t for w in words for t in tokens(w.text)} and clarity(words) >= CLARITY_OK
