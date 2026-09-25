from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import courses
from app.models import Assessment, Attempt, AttemptStatus, Level, Skill, User
from app.schemas.attempt import LevelOut, RecommendationOut
from app.schemas.progress import (
    AttemptSummaryOut,
    ProgressOut,
    SkillTrendOut,
    TeacherAttemptOut,
)

HISTORY_LIMIT = 50
FINISHED = (AttemptStatus.SUBMITTED, AttemptStatus.EXPIRED)


def skill_pcts(attempt: Attempt) -> dict[str, float]:
    return {code: v["pct"] for code, v in (attempt.skill_breakdown or {}).items() if code[0] != "_"}


async def get_progress(session: AsyncSession, user: User) -> ProgressOut:
    # Usa el índice (user_id, submitted_at) y solo trae el historial reciente.
    rows = (
        await session.execute(
            select(Attempt, Assessment.title)
            .join(Assessment, Assessment.id == Attempt.assessment_id)
            .where(Attempt.user_id == user.id, Attempt.status.in_(FINISHED))
            .order_by(Attempt.submitted_at.desc())
            .limit(HISTORY_LIMIT)
        )
    ).all()

    attempts = [
        AttemptSummaryOut(
            id=a.id,
            assessment_title=title,
            status=a.status,
            submitted_at=a.submitted_at,
            duration_seconds=int((a.submitted_at - a.started_at).total_seconds()),
            score_pct=float(a.score_pct),
            correct_count=a.correct_count,
            suggested_level=a.suggested_level_code,
            skills=skill_pcts(a),
        )
        for a, title in rows
    ]
    if not attempts:
        return ProgressOut(
            total_attempts=0,
            best_score_pct=None,
            average_score_pct=None,
            current_level=None,
            skills=[],
            attempts=[],
        )

    level = await session.get(Level, attempts[0].suggested_level)
    skill_names = dict((await session.execute(select(Skill.code, Skill.name))).all())

    skills = []
    for code in attempts[0].skills:
        history = [a.skills[code] for a in attempts if code in a.skills]
        skills.append(
            SkillTrendOut(
                code=code,
                name=skill_names.get(code, code),
                latest_pct=history[0],
                previous_pct=history[1] if len(history) > 1 else None,
                average_pct=round(sum(history) / len(history), 2),
            )
        )

    scores = [a.score_pct for a in attempts]
    return ProgressOut(
        total_attempts=len(attempts),
        best_score_pct=max(scores),
        average_score_pct=round(sum(scores) / len(scores), 2),
        current_level=LevelOut(code=level.code, name=level.name, description=level.description),
        skills=skills,
        attempts=attempts,
        recommendation=RecommendationOut(
            **courses.recommend(level.code, [(s.name, s.latest_pct) for s in skills])
        ),
    )


async def list_recent_attempts(session: AsyncSession, limit: int) -> list[TeacherAttemptOut]:
    rows = (
        await session.execute(
            select(Attempt, User.full_name, User.email, Assessment.title)
            .join(User, User.id == Attempt.user_id)
            .join(Assessment, Assessment.id == Attempt.assessment_id)
            .where(Attempt.status.in_(FINISHED))
            .order_by(Attempt.submitted_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        TeacherAttemptOut(
            id=a.id,
            student_name=name,
            student_email=email,
            assessment_title=title,
            status=a.status,
            submitted_at=a.submitted_at,
            score_pct=float(a.score_pct),
            suggested_level=a.suggested_level_code,
            integrity_flags=a.integrity_flags,
        )
        for a, name, email, title in rows
    ]
