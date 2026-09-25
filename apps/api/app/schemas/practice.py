from typing import Annotated

from pydantic import BaseModel, Field

from app.domain.practice import MAX_TURNS


class LessonOut(BaseModel):
    id: str
    sound: str
    word: str
    tip: str
    question: str
    max_turns: int


class HeardOut(BaseModel):
    text: str
    ok: bool | None = None  # solo al decir la palabra de la clase
    unclear: list[str] = []  # palabras que no se entendieron bien: a practicar


class ReplyIn(BaseModel):
    # Alterna Glo/estudiante empezando por la pregunta de Glo; el tope acota tokens por sesión.
    turns: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        min_length=2, max_length=2 * MAX_TURNS
    )


class ReplyOut(BaseModel):
    text: str
    fix: str | None  # tu frase corregida, si tenía errores
    why: str | None  # por qué, en español
    audio: str | None  # mp3 en base64; None si la voz no está configurada
    done: bool
