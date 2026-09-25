import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models import AttemptStatus
from app.schemas.attempt import AttemptResultOut, LevelOut, RecommendationOut


class AttemptSummaryOut(BaseModel):
    id: uuid.UUID
    assessment_title: str
    status: AttemptStatus
    submitted_at: datetime
    duration_seconds: int
    score_pct: float
    correct_count: int
    suggested_level: str
    skills: dict[str, float]  # {"grammar": 80.0, ...}


class SkillTrendOut(BaseModel):
    code: str
    name: str
    latest_pct: float
    previous_pct: float | None
    average_pct: float


class ProgressOut(BaseModel):
    total_attempts: int
    best_score_pct: float | None
    average_score_pct: float | None
    current_level: LevelOut | None
    skills: list[SkillTrendOut]
    attempts: list[AttemptSummaryOut]  # más reciente primero
    recommendation: RecommendationOut | None = None  # curso según el último intento


class TeacherAttemptOut(BaseModel):
    id: uuid.UUID
    student_name: str
    student_email: str
    assessment_title: str
    status: AttemptStatus
    submitted_at: datetime
    score_pct: float
    suggested_level: str
    integrity_flags: int


class TeacherStudentOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    attempts: int
    last_attempt_id: uuid.UUID | None
    last_submitted_at: datetime | None
    last_score_pct: float | None
    previous_score_pct: float | None
    best_score_pct: float | None
    level: str | None
    skills: dict[str, float]  # último intento
    integrity_flags: int  # señales sospechosas en todos sus intentos
    alert: str | None  # severidad de la alerta de su último intento: high | medium


class AlertReasonOut(BaseModel):
    kind: str  # integrity | rushed | expired | low_score | score_drop
    severity: str  # high | medium
    message: str


class TeacherAlertOut(BaseModel):
    """Una alerta por estudiante: su último intento y todos los motivos."""

    attempt_id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    submitted_at: datetime
    score_pct: float
    severity: str
    reasons: list[AlertReasonOut]
    events: dict[str, int]  # {"tab_hidden": 3, "paste": 1}


class CountOut(BaseModel):
    code: str
    name: str
    value: float


class ActivityDayOut(BaseModel):
    date: date
    attempts: int
    average_score_pct: float | None


class TeacherOverviewOut(BaseModel):
    total_students: int
    evaluated_students: int
    total_attempts: int
    average_score_pct: float | None
    in_progress: int
    flagged_attempts: int
    levels: list[CountOut]  # estudiantes por nivel actual (value = cantidad)
    skills: list[CountOut]  # promedio del grupo por habilidad (value = %)
    activity: list[ActivityDayOut]  # últimos ACTIVITY_DAYS días, incluidos los días sin intentos
    students: list[TeacherStudentOut]
    alerts: list[TeacherAlertOut]


class StudentOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str


class TeacherStudentDetailOut(BaseModel):
    student: StudentOut
    progress: ProgressOut


class AttemptEventOut(BaseModel):
    type: str
    occurred_at: datetime
    question_position: int | None


class TeacherAttemptDetailOut(BaseModel):
    student: StudentOut
    status: AttemptStatus
    integrity_flags: int
    events: list[AttemptEventOut]
    attempt: AttemptResultOut
