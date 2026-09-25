import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamps, UUIDPk, str_enum


class AttemptStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    EXPIRED = "expired"


class Attempt(UUIDPk, Timestamps, Base):
    """Un intento de un estudiante sobre una evaluación.

    Mientras está IN_PROGRESS las respuestas se autoguardan (reanudable tras perder conexión).
    Al enviarse, el servidor calcula el resultado y lo congela aquí (snapshot inmutable).
    """

    __tablename__ = "attempts"
    __table_args__ = (
        # Un solo intento abierto por estudiante y evaluación.
        Index(
            "uq_attempts_open_per_user",
            "user_id",
            "assessment_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
        ),
        Index("ix_attempts_user_submitted", "user_id", "submitted_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    assessment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessments.id"))
    status: Mapped[AttemptStatus] = mapped_column(
        str_enum(AttemptStatus), default=AttemptStatus.IN_PROGRESS
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Orden generado por el servidor para ESTE intento (anti-trampa: cada estudiante ve
    # un orden distinto). {"questions": [question_id, ...], "options": {question_id: ["c","a",...]}}
    layout: Mapped[dict[str, Any]] = mapped_column(JSONB)
    integrity_flags: Mapped[int] = mapped_column(SmallInteger, default=0)

    # Resultado (se llena solo en el servidor al enviar)
    score_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    correct_count: Mapped[int | None] = mapped_column(SmallInteger)
    incorrect_count: Mapped[int | None] = mapped_column(SmallInteger)
    suggested_level_code: Mapped[str | None] = mapped_column(ForeignKey("levels.code"))
    # {"grammar": {"correct": 4, "total": 5, "pct": 80.0}, ...}
    skill_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ai_feedback: Mapped[str | None] = mapped_column(Text)

    answers: Mapped[list["AttemptAnswer"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )
    events: Mapped[list["AttemptEvent"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )


class AttemptAnswer(UUIDPk, Timestamps, Base):
    __tablename__ = "attempt_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id"),)

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attempts.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"))
    # choice -> {"option_id": "b"} | text -> {"text": "since"}
    # speech -> {"transcript": "...", "score": 0.82, "tries": 1, ...} (lo escribe el servidor)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_correct: Mapped[bool | None]  # None hasta que el intento se envía

    attempt: Mapped[Attempt] = relationship(back_populates="answers")


class IntegrityEventType(StrEnum):
    TAB_HIDDEN = "tab_hidden"
    WINDOW_BLUR = "window_blur"
    PASTE = "paste"
    COPY = "copy"
    FULLSCREEN_EXIT = "fullscreen_exit"
    RESUMED = "resumed"  # reanudó tras desconexión o recarga
    # Derivadas por el servidor al calificar (ver attempt_service._derived_signals). El cliente
    # no puede enviarlas: se calculan con horas del servidor, no con lo que diga el navegador.
    RAPID_ANSWER = "rapid_answer"
    ANSWERED_AFTER_LEAVING = "answered_after_leaving"


SERVER_ONLY_EVENTS = {IntegrityEventType.RAPID_ANSWER, IntegrityEventType.ANSWERED_AFTER_LEAVING}


class AttemptEvent(UUIDPk, Base):
    """Bitácora de integridad del intento. No bloquea al estudiante: deja evidencia
    para que un profesor revise intentos sospechosos."""

    __tablename__ = "attempt_events"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attempts.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[IntegrityEventType] = mapped_column(str_enum(IntegrityEventType))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    question_id: Mapped[uuid.UUID | None]
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    attempt: Mapped[Attempt] = relationship(back_populates="events")
