"""Vista del profesor: panorama del grupo, alertas y detalle de estudiantes e intentos.

Las reglas de alerta viven aquí (no en el frontend) para que cualquier cliente —panel web,
correo semanal, app móvil— muestre exactamente las mismas.
"""

import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import (
    Assessment,
    Attempt,
    AttemptEvent,
    AttemptStatus,
    IntegrityEventType,
    Level,
    Role,
    Skill,
    User,
)
from app.schemas.progress import (
    ActivityDayOut,
    AlertReasonOut,
    AttemptEventOut,
    CountOut,
    StudentOut,
    TeacherAlertOut,
    TeacherAttemptDetailOut,
    TeacherOverviewOut,
    TeacherStudentDetailOut,
    TeacherStudentOut,
)
from app.services import attempt_service, progress_service

FINISHED = (AttemptStatus.SUBMITTED, AttemptStatus.EXPIRED)
# ponytail: se agregan en memoria los últimos N intentos; con miles de estudiantes, pasar a
# una tabla de resumen por estudiante (actualizada al enviar) y paginar por grupo/profesor.
WINDOW = 2000

INTEGRITY_MEDIUM = 3  # señales (cambio de pestaña, pegar, salir de pantalla completa...)
INTEGRITY_HIGH = 6
RUSHED_RATIO = 0.2  # terminó en menos del 20 % del tiempo disponible
LOW_SCORE = 40
SCORE_DROP = 15
RAPID_ALERT = 3  # respuestas en menos de 3 s (ver attempt_service.RAPID_MAX)
ACTIVITY_DAYS = 14


def _student_out(user: User) -> StudentOut:
    return StudentOut(id=user.id, full_name=user.full_name, email=user.email)


def suspicious(events: dict[str, int]) -> int:
    """Reanudar tras un corte de red no es trampa: no cuenta como señal."""
    return sum(n for kind, n in events.items() if kind != IntegrityEventType.RESUMED)


def _alert_for(
    attempt: Attempt,
    user: User,
    events: dict[str, int],
    time_limit: int | None,
    previous_score: float | None,
) -> TeacherAlertOut | None:
    score = float(attempt.score_pct)
    duration = (attempt.submitted_at - attempt.started_at).total_seconds()
    rapid = events.get(IntegrityEventType.RAPID_ANSWER, 0)
    after_leaving = events.get(IntegrityEventType.ANSWERED_AFTER_LEAVING, 0)
    signals = suspicious(events) - rapid - after_leaving  # esas dos tienen su propio motivo
    reasons: list[AlertReasonOut] = []

    def add(kind: str, severity: str, message: str) -> None:
        reasons.append(AlertReasonOut(kind=kind, severity=severity, message=message))

    if signals >= INTEGRITY_MEDIUM:
        severity = "high" if signals >= INTEGRITY_HIGH else "medium"
        add("integrity", severity, f"{signals} señales de posible ayuda externa")
    if after_leaving:
        n = after_leaving
        add(
            "answered_after_leaving",
            "high",
            f"Salió de la evaluación y al volver cambió {n} respuesta{'s' if n > 1 else ''}",
        )
    if rapid >= RAPID_ALERT:
        add("rapid", "medium", f"{rapid} respuestas en menos de 3 segundos, sin tiempo para leer")
    if time_limit and duration < time_limit * 60 * RUSHED_RATIO:
        add("rushed", "medium", f"Terminó en {max(1, round(duration / 60))} de {time_limit} min")
    if attempt.status == AttemptStatus.EXPIRED:
        add("expired", "medium", "Se le acabó el tiempo antes de enviar")
    if score < LOW_SCORE:
        add("low_score", "high", "Puntaje bajo: necesita acompañamiento")
    if previous_score is not None and previous_score - score >= SCORE_DROP:
        add("score_drop", "medium", f"Bajó {round(previous_score - score)} puntos vs. el anterior")

    if not reasons:
        return None
    return TeacherAlertOut(
        attempt_id=attempt.id,
        student_id=user.id,
        student_name=user.full_name,
        submitted_at=attempt.submitted_at,
        score_pct=score,
        severity="high" if any(r.severity == "high" for r in reasons) else "medium",
        reasons=reasons,
        events=events,
    )


async def overview(session: AsyncSession) -> TeacherOverviewOut:
    students = list(
        await session.scalars(
            select(User).where(User.role == Role.STUDENT).order_by(User.full_name)
        )
    )
    rows = (
        await session.execute(
            select(Attempt, Assessment.time_limit_minutes)
            .join(Assessment, Assessment.id == Attempt.assessment_id)
            .where(Attempt.status.in_(FINISHED))
            .order_by(Attempt.submitted_at.desc())
            .limit(WINDOW)
        )
    ).all()

    events: dict[uuid.UUID, dict[str, int]] = defaultdict(dict)
    flagged = [a.id for a, _ in rows if a.integrity_flags]
    if flagged:
        for attempt_id, kind, n in await session.execute(
            select(AttemptEvent.attempt_id, AttemptEvent.type, func.count())
            .where(AttemptEvent.attempt_id.in_(flagged))
            .group_by(AttemptEvent.attempt_id, AttemptEvent.type)
        ):
            events[attempt_id][str(kind)] = n

    now = datetime.now(UTC)
    in_progress = await session.scalar(
        select(func.count()).where(
            Attempt.status == AttemptStatus.IN_PROGRESS,
            or_(Attempt.expires_at.is_(None), Attempt.expires_at > now),
        )
    )

    by_student: dict[uuid.UUID, list[tuple[Attempt, int | None]]] = defaultdict(list)
    for attempt, limit in rows:
        by_student[attempt.user_id].append((attempt, limit))  # más reciente primero

    alerts: list[TeacherAlertOut] = []
    student_rows: list[TeacherStudentOut] = []
    level_counts: Counter[str] = Counter()
    skill_sums: dict[str, list[float]] = defaultdict(list)

    for user in students:
        history = by_student.get(user.id, [])
        # Alertas solo del último intento: lo que el profesor debe atender hoy.
        # Los intentos anteriores siguen visibles en el detalle del estudiante.
        alert = None
        if history:
            attempt, limit = history[0]
            previous = float(history[1][0].score_pct) if len(history) > 1 else None
            alert = _alert_for(attempt, user, events.get(attempt.id, {}), limit, previous)
        if alert:
            alerts.append(alert)

        last = history[0][0] if history else None
        skills = progress_service.skill_pcts(last) if last else {}
        if last:
            level_counts[last.suggested_level_code] += 1
            for code, pct in skills.items():
                skill_sums[code].append(pct)
        scores = [float(a.score_pct) for a, _ in history]
        student_rows.append(
            TeacherStudentOut(
                id=user.id,
                full_name=user.full_name,
                email=user.email,
                attempts=len(history),
                last_attempt_id=last.id if last else None,
                last_submitted_at=last.submitted_at if last else None,
                last_score_pct=scores[0] if scores else None,
                previous_score_pct=scores[1] if len(scores) > 1 else None,
                best_score_pct=max(scores) if scores else None,
                level=last.suggested_level_code if last else None,
                skills=skills,
                integrity_flags=sum(suspicious(events.get(a.id, {})) for a, _ in history),
                alert=alert.severity if alert else None,
            )
        )

    levels = (await session.execute(select(Level.code, Level.name).order_by(Level.rank))).all()
    skill_names = (await session.execute(select(Skill.code, Skill.name))).all()
    all_scores = [float(a.score_pct) for a, _ in rows]
    alerts.sort(key=lambda a: (a.severity != "high", -a.submitted_at.timestamp()))

    by_day: dict = defaultdict(list)
    for attempt, _ in rows:
        by_day[attempt.submitted_at.date()].append(float(attempt.score_pct))
    today = now.date()
    activity = [
        ActivityDayOut(
            date=day,
            attempts=len(scores := by_day.get(day, [])),
            average_score_pct=round(sum(scores) / len(scores), 1) if scores else None,
        )
        for day in (today - timedelta(days=i) for i in range(ACTIVITY_DAYS - 1, -1, -1))
    ]

    return TeacherOverviewOut(
        total_students=len(students),
        evaluated_students=sum(1 for s in student_rows if s.attempts),
        total_attempts=len(rows),
        average_score_pct=round(sum(all_scores) / len(all_scores), 1) if all_scores else None,
        in_progress=in_progress or 0,
        flagged_attempts=sum(
            1 for a, _ in rows if suspicious(events.get(a.id, {})) >= INTEGRITY_MEDIUM
        ),
        levels=[CountOut(code=c, name=n, value=level_counts[c]) for c, n in levels],
        skills=[
            CountOut(code=c, name=n, value=round(sum(v) / len(v), 1))
            for c, n in skill_names
            if (v := skill_sums.get(c))
        ],
        activity=activity,
        students=student_rows,
        alerts=alerts,
    )


async def student_detail(session: AsyncSession, student_id: uuid.UUID) -> TeacherStudentDetailOut:
    user = await session.get(User, student_id)
    if not user or user.role != Role.STUDENT:
        raise NotFoundError("Estudiante no encontrado")
    return TeacherStudentDetailOut(
        student=_student_out(user), progress=await progress_service.get_progress(session, user)
    )


async def attempt_detail(session: AsyncSession, attempt_id: uuid.UUID) -> TeacherAttemptDetailOut:
    attempt = await session.get(Attempt, attempt_id)
    if not attempt:
        raise NotFoundError("Intento no encontrado")
    result = await attempt_service.result_view(session, attempt)  # 409 si sigue abierto
    user = await session.get(User, attempt.user_id)
    positions = {qid: i for i, qid in enumerate(attempt.layout["questions"], start=1)}
    events = await session.scalars(
        select(AttemptEvent)
        .where(AttemptEvent.attempt_id == attempt.id)
        .order_by(AttemptEvent.occurred_at)
    )
    return TeacherAttemptDetailOut(
        student=_student_out(user),
        status=attempt.status,
        integrity_flags=attempt.integrity_flags,
        events=[
            AttemptEventOut(
                type=e.type,
                occurred_at=e.occurred_at,
                question_position=positions.get(str(e.question_id)) if e.question_id else None,
            )
            for e in events
        ],
        attempt=result,
    )
