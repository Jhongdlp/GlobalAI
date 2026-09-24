import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamps, UUIDPk, str_enum


class QuestionType(StrEnum):
    MULTIPLE_CHOICE = "multiple_choice"
    FILL_BLANK = "fill_blank"
    COMPREHENSION = "comprehension"
    VOCABULARY = "vocabulary"


class ResponseFormat(StrEnum):
    CHOICE = "choice"  # el estudiante elige una opción
    TEXT = "text"  # el estudiante escribe la respuesta


class StimulusKind(StrEnum):
    TEXT = "text"  # Reading: el texto se envía al cliente
    AUDIO = "audio"  # Listening: solo se envía el audio, nunca la transcripción


class Stimulus(UUIDPk, Timestamps, Base):
    """Material compartido por una o más preguntas (lectura o audio)."""

    __tablename__ = "stimuli"

    code: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[StimulusKind] = mapped_column(str_enum(StimulusKind))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)  # texto de lectura o transcripción del audio
    audio_url: Mapped[str | None] = mapped_column(String(500))


class Question(UUIDPk, Timestamps, Base):
    """Pregunta del banco. Es independiente de las evaluaciones para poder reutilizarla."""

    __tablename__ = "questions"

    code: Mapped[str] = mapped_column(String(64), unique=True)
    type: Mapped[QuestionType] = mapped_column(str_enum(QuestionType))
    response_format: Mapped[ResponseFormat] = mapped_column(str_enum(ResponseFormat))
    skill_code: Mapped[str] = mapped_column(ForeignKey("skills.code"), index=True)
    level_code: Mapped[str] = mapped_column(ForeignKey("levels.code"), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    # [{"id": "a", "text": "..."}] solo para response_format=choice
    options: Mapped[list[dict[str, str]] | None] = mapped_column(JSONB)
    # SENSIBLE: nunca se serializa hacia el cliente antes del envío del intento.
    # choice -> {"option_id": "b"} | text -> {"accepted": ["since"]}
    answer_key: Mapped[dict[str, Any]] = mapped_column(JSONB)
    explanation: Mapped[str | None] = mapped_column(Text)
    stimulus_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stimuli.id"))
    is_active: Mapped[bool] = mapped_column(default=True)

    stimulus: Mapped[Stimulus | None] = relationship(lazy="joined")


class Assessment(UUIDPk, Timestamps, Base):
    __tablename__ = "assessments"

    slug: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    # Nivel objetivo; None = prueba de ubicación que abarca varios niveles.
    level_code: Mapped[str | None] = mapped_column(ForeignKey("levels.code"))
    time_limit_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    # Anti-trampa: intentos máximos (None = ilimitado) y espera mínima entre intentos.
    max_attempts: Mapped[int | None] = mapped_column(SmallInteger)
    cooldown_minutes: Mapped[int] = mapped_column(SmallInteger, default=0)
    shuffle_questions: Mapped[bool] = mapped_column(default=True)
    shuffle_options: Mapped[bool] = mapped_column(default=True)
    is_published: Mapped[bool] = mapped_column(default=False)

    items: Mapped[list["AssessmentQuestion"]] = relationship(
        back_populates="assessment",
        order_by="AssessmentQuestion.position",
        cascade="all, delete-orphan",
    )


class AssessmentQuestion(Base):
    """Qué preguntas componen una evaluación, en qué orden y con qué peso."""

    __tablename__ = "assessment_questions"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"), primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    points: Mapped[int] = mapped_column(SmallInteger, default=1)

    assessment: Mapped[Assessment] = relationship(back_populates="items")
    question: Mapped[Question] = relationship(lazy="joined")
