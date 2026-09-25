"""DTOs del flujo de evaluación.

Regla de seguridad: ningún schema de salida previo al envío incluye `answer_key`,
`explanation` ni la transcripción de un audio. Los DTOs se construyen explícitamente
(no con from_attributes sobre el modelo) para que un campo nuevo del modelo nunca
se filtre por accidente al cliente.
"""

import uuid
from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import AttemptStatus, IntegrityEventType, QuestionType, ResponseFormat, StimulusKind
from app.models.attempt import SERVER_ONLY_EVENTS


class AssessmentSummaryOut(BaseModel):
    slug: str
    title: str
    description: str | None
    question_count: int
    time_limit_minutes: int | None
    max_attempts: int | None
    attempts_used: int
    best_score_pct: float | None
    open_attempt_id: uuid.UUID | None
    available_at: datetime | None  # espera entre intentos; None = puede empezar ya


class OptionOut(BaseModel):
    id: str
    text: str


class StimulusOut(BaseModel):
    id: uuid.UUID
    kind: StimulusKind
    title: str
    content: str | None = None  # solo para lecturas
    audio_url: str | None = None  # solo para audios


class QuestionOut(BaseModel):
    id: uuid.UUID
    position: int
    type: QuestionType
    response_format: ResponseFormat
    skill: str
    level: str
    prompt: str
    options: list[OptionOut] | None
    stimulus: StimulusOut | None


class AnswerIn(BaseModel):
    option_id: str | None = Field(default=None, max_length=8)
    text: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def exactly_one(self) -> Self:
        if (self.option_id is None) == (self.text is None):
            raise ValueError("Envía option_id o text (solo uno)")
        return self

    def as_response(self) -> dict[str, Any]:
        return {"option_id": self.option_id} if self.option_id is not None else {"text": self.text}


class SubmitIn(BaseModel):
    """Envío final. Puede incluir respuestas que el cliente guardó offline y no alcanzó a
    sincronizar; el servidor las acepta solo si el intento sigue dentro del tiempo."""

    answers: dict[uuid.UUID, AnswerIn] = Field(default_factory=dict, max_length=200)


class IntegrityEventIn(BaseModel):
    type: IntegrityEventType
    occurred_at: datetime
    question_id: uuid.UUID | None = None

    @field_validator("type")
    @classmethod
    def client_reportable(cls, value: IntegrityEventType) -> IntegrityEventType:
        if value in SERVER_ONLY_EVENTS:
            raise ValueError("Este tipo de evento lo calcula el servidor")
        return value


class IntegrityEventsIn(BaseModel):
    events: list[IntegrityEventIn] = Field(max_length=100)


class LevelOut(BaseModel):
    code: str
    name: str
    description: str | None


class SkillScoreOut(BaseModel):
    code: str
    name: str
    correct: int
    total: int
    pct: float


class RecommendationOut(BaseModel):
    course: str
    level: str
    weeks: int
    promise: str
    focus: list[str]
    script: str  # lo que Glo dice en voz alta


class ResultOut(BaseModel):
    score_pct: float
    correct_count: int
    incorrect_count: int
    unanswered_count: int
    suggested_level: LevelOut
    skills: list[SkillScoreOut]
    submitted_at: datetime
    duration_seconds: int
    ai_feedback: str | None
    recommendation: RecommendationOut


class ReviewItemOut(BaseModel):
    question: QuestionOut
    response: dict[str, Any] | None
    is_correct: bool
    correct_answer: str  # texto legible de la respuesta correcta
    explanation: str | None
    transcript: str | None = None  # para Listening, solo después de enviar


class AttemptOut(BaseModel):
    id: uuid.UUID
    status: AttemptStatus
    assessment_slug: str
    assessment_title: str
    started_at: datetime
    expires_at: datetime | None
    server_time: datetime  # el cliente calcula el temporizador contra la hora del servidor
    questions: list[QuestionOut]
    answers: dict[uuid.UUID, dict[str, Any]]
    result: ResultOut | None = None


class AttemptResultOut(BaseModel):
    id: uuid.UUID
    assessment_title: str
    result: ResultOut
    review: list[ReviewItemOut]


class AnswerSavedOut(BaseModel):
    question_id: uuid.UUID
    saved_at: datetime


class SpeechSavedOut(BaseModel):
    question_id: uuid.UUID
    saved_at: datetime
    transcript: str
    tries_left: int


class FeedbackOut(BaseModel):
    feedback: str
