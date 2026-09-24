import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import AttemptStatus
from app.schemas.attempt import LevelOut


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
