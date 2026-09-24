"""Casos de uso del intento de evaluación. Toda la lógica sensible vive aquí, en el servidor:
el cliente nunca recibe respuestas correctas antes del envío ni puede fijar su puntaje."""

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, ConflictError, NotFoundError
from app.domain.scoring import GradableItem, grade, suggest_level
from app.models import (
    Assessment,
    AssessmentQuestion,
    Attempt,
    AttemptAnswer,
    AttemptEvent,
    AttemptStatus,
    Level,
    Question,
    ResponseFormat,
    Skill,
    StimulusKind,
    User,
)
from app.schemas.attempt import (
    AnswerIn,
    AssessmentSummaryOut,
    AttemptOut,
    AttemptResultOut,
    IntegrityEventsIn,
    LevelOut,
    OptionOut,
    QuestionOut,
    ResultOut,
    ReviewItemOut,
    SkillScoreOut,
    StimulusOut,
    SubmitIn,
)

# Tolerancia de red: respuestas que llegan unos segundos después del límite se aceptan.
EXPIRY_GRACE = timedelta(seconds=30)


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------


async def list_assessments(session: AsyncSession, user: User) -> list[AssessmentSummaryOut]:
    question_counts = (
        select(AssessmentQuestion.assessment_id, func.count().label("n"))
        .group_by(AssessmentQuestion.assessment_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Assessment, question_counts.c.n)
            .join(question_counts, question_counts.c.assessment_id == Assessment.id)
            .where(Assessment.is_published)
            .order_by(Assessment.created_at)
        )
    ).all()

    stats = {
        row.assessment_id: row
        for row in (
            await session.execute(
                select(
                    Attempt.assessment_id,
                    func.count().filter(Attempt.status != AttemptStatus.IN_PROGRESS).label("used"),
                    func.max(Attempt.score_pct).label("best"),
                )
                .where(Attempt.user_id == user.id)
                .group_by(Attempt.assessment_id)
            )
        ).all()
    }
    open_ids = dict(
        (
            await session.execute(
                select(Attempt.assessment_id, Attempt.id).where(
                    Attempt.user_id == user.id, Attempt.status == AttemptStatus.IN_PROGRESS
                )
            )
        ).all()
    )

    result = []
    for assessment, n in rows:
        s = stats.get(assessment.id)
        result.append(
            AssessmentSummaryOut(
                slug=assessment.slug,
                title=assessment.title,
                description=assessment.description,
                question_count=n,
                time_limit_minutes=assessment.time_limit_minutes,
                max_attempts=assessment.max_attempts,
                attempts_used=s.used if s else 0,
                best_score_pct=float(s.best) if s and s.best is not None else None,
                open_attempt_id=open_ids.get(assessment.id),
            )
        )
    return result


async def _get_published_assessment(session: AsyncSession, slug: str) -> Assessment:
    assessment = await session.scalar(
        select(Assessment)
        .where(Assessment.slug == slug, Assessment.is_published)
        .options(selectinload(Assessment.items))
    )
    if not assessment:
        raise NotFoundError("La evaluación no existe o no está disponible")
    return assessment


async def _get_own_attempt(
    session: AsyncSession, user: User, attempt_id: uuid.UUID, *, lock: bool = False
) -> Attempt:
    stmt = select(Attempt).where(Attempt.id == attempt_id, Attempt.user_id == user.id)
    if lock:
        stmt = stmt.with_for_update()
    attempt = await session.scalar(stmt)
    if not attempt:
        # 404 también si el intento es de otro usuario: no revelamos que existe.
        raise NotFoundError("Intento no encontrado")
    return attempt


async def _load_questions(session: AsyncSession, attempt: Attempt) -> list[Question]:
    ids = [uuid.UUID(q) for q in attempt.layout["questions"]]
    by_id = {q.id: q for q in (await session.scalars(select(Question).where(Question.id.in_(ids))))}
    return [by_id[qid] for qid in ids]


async def _saved_answers(session: AsyncSession, attempt_id: uuid.UUID) -> list[AttemptAnswer]:
    return list(
        await session.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt_id))
    )


def _is_expired(attempt: Attempt, now: datetime) -> bool:
    return attempt.expires_at is not None and now > attempt.expires_at + EXPIRY_GRACE


# ---------------------------------------------------------------------------
# Serialización segura (sin respuestas correctas)
# ---------------------------------------------------------------------------


def _question_out(question: Question, position: int, option_order: list[str] | None) -> QuestionOut:
    options = None
    if question.options:
        by_id = {o["id"]: o for o in question.options}
        order = option_order or list(by_id)
        options = [OptionOut(id=oid, text=by_id[oid]["text"]) for oid in order]

    stimulus = None
    if question.stimulus:
        s = question.stimulus
        is_text = s.kind == StimulusKind.TEXT
        stimulus = StimulusOut(
            id=s.id,
            kind=s.kind,
            title=s.title,
            content=s.content if is_text else None,  # la transcripción del audio no sale
            audio_url=None if is_text else f"/api/v1/stimuli/{s.id}/audio",
        )

    return QuestionOut(
        id=question.id,
        position=position,
        type=question.type,
        response_format=question.response_format,
        skill=question.skill_code,
        level=question.level_code,
        prompt=question.prompt,
        options=options,
        stimulus=stimulus,
    )


def _questions_out(attempt: Attempt, questions: list[Question]) -> list[QuestionOut]:
    option_orders = attempt.layout.get("options", {})
    return [
        _question_out(q, i, option_orders.get(str(q.id))) for i, q in enumerate(questions, start=1)
    ]


async def _result_out(session: AsyncSession, attempt: Attempt) -> ResultOut:
    level = await session.get(Level, attempt.suggested_level_code)
    skill_names = dict((await session.execute(select(Skill.code, Skill.name))).all())
    breakdown = attempt.skill_breakdown or {}
    return ResultOut(
        score_pct=float(attempt.score_pct or 0),
        correct_count=attempt.correct_count or 0,
        incorrect_count=attempt.incorrect_count or 0,
        unanswered_count=breakdown.get("_meta", {}).get("unanswered", 0),
        suggested_level=LevelOut(code=level.code, name=level.name, description=level.description),
        skills=[
            SkillScoreOut(code=code, name=skill_names.get(code, code), **values)
            for code, values in breakdown.items()
            if not code.startswith("_")
        ],
        submitted_at=attempt.submitted_at,
        duration_seconds=int((attempt.submitted_at - attempt.started_at).total_seconds()),
        ai_feedback=attempt.ai_feedback,
    )


async def build_attempt_view(session: AsyncSession, attempt: Attempt) -> AttemptOut:
    assessment = await session.get(Assessment, attempt.assessment_id)
    questions = await _load_questions(session, attempt)
    answers = await _saved_answers(session, attempt.id)
    return AttemptOut(
        id=attempt.id,
        status=attempt.status,
        assessment_slug=assessment.slug,
        assessment_title=assessment.title,
        started_at=attempt.started_at,
        expires_at=attempt.expires_at,
        server_time=_now(),
        questions=_questions_out(attempt, questions),
        answers={a.question_id: a.response for a in answers},
        result=await _result_out(session, attempt)
        if attempt.status != AttemptStatus.IN_PROGRESS
        else None,
    )


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def _build_layout(assessment: Assessment, questions: dict[uuid.UUID, Question]) -> dict[str, Any]:
    rng = random.SystemRandom()
    items = list(assessment.items)
    if assessment.shuffle_questions:
        rng.shuffle(items)
    options: dict[str, list[str]] = {}
    for item in items:
        q = questions[item.question_id]
        if q.options:
            ids = [o["id"] for o in q.options]
            if assessment.shuffle_options:
                rng.shuffle(ids)
            options[str(q.id)] = ids
    return {
        "questions": [str(i.question_id) for i in items],
        "options": options,
        "points": {str(i.question_id): i.points for i in items},
    }


async def start_or_resume(session: AsyncSession, user: User, slug: str) -> Attempt:
    assessment = await _get_published_assessment(session, slug)
    now = _now()

    open_attempt = await session.scalar(
        select(Attempt).where(
            Attempt.user_id == user.id,
            Attempt.assessment_id == assessment.id,
            Attempt.status == AttemptStatus.IN_PROGRESS,
        )
    )
    if open_attempt and not _is_expired(open_attempt, now):
        return open_attempt  # reanudar: mismo orden, respuestas guardadas intactas
    if open_attempt:
        await _finalize(session, open_attempt, status=AttemptStatus.EXPIRED)

    finished = (
        await session.execute(
            select(func.count(), func.max(Attempt.submitted_at)).where(
                Attempt.user_id == user.id,
                Attempt.assessment_id == assessment.id,
                Attempt.status != AttemptStatus.IN_PROGRESS,
            )
        )
    ).one()
    used, last_submitted = finished
    if assessment.max_attempts is not None and used >= assessment.max_attempts:
        raise ConflictError(
            "Ya usaste todos los intentos de esta evaluación", code="attempt_limit_reached"
        )
    if assessment.cooldown_minutes and last_submitted:
        available_at = last_submitted + timedelta(minutes=assessment.cooldown_minutes)
        if now < available_at:
            raise ConflictError(
                "Debes esperar antes de un nuevo intento",
                code="cooldown_active",
                details={"available_at": available_at.isoformat()},
            )

    questions = {
        q.id: q
        for q in await session.scalars(
            select(Question).where(Question.id.in_([i.question_id for i in assessment.items]))
        )
    }
    attempt = Attempt(
        user_id=user.id,
        assessment_id=assessment.id,
        status=AttemptStatus.IN_PROGRESS,
        started_at=now,
        expires_at=now + timedelta(minutes=assessment.time_limit_minutes)
        if assessment.time_limit_minutes
        else None,
        layout=_build_layout(assessment, questions),
        integrity_flags=0,
    )
    session.add(attempt)
    try:
        await session.commit()
    except IntegrityError:
        # Doble clic / dos pestañas: el índice parcial único garantiza un solo intento abierto.
        await session.rollback()
        return await start_or_resume(session, user, slug)
    return attempt


async def get_attempt(session: AsyncSession, user: User, attempt_id: uuid.UUID) -> Attempt:
    attempt = await _get_own_attempt(session, user, attempt_id)
    if attempt.status == AttemptStatus.IN_PROGRESS and _is_expired(attempt, _now()):
        await _finalize(session, attempt, status=AttemptStatus.EXPIRED)
        await session.commit()
    return attempt


def _validate_answer(question: Question, answer: AnswerIn, option_ids: list[str]) -> None:
    if question.response_format == ResponseFormat.CHOICE:
        if answer.option_id is None or answer.option_id not in option_ids:
            raise AppError("Opción inválida para esta pregunta", code="invalid_answer")
    elif answer.text is None:
        raise AppError("Esta pregunta requiere una respuesta escrita", code="invalid_answer")


async def _upsert_answers(
    session: AsyncSession, attempt: Attempt, answers: dict[uuid.UUID, AnswerIn]
) -> None:
    if not answers:
        return
    layout_ids = set(attempt.layout["questions"])
    unknown = [str(qid) for qid in answers if str(qid) not in layout_ids]
    if unknown:
        raise AppError(
            "La pregunta no pertenece a este intento", code="invalid_question", details=unknown
        )

    questions = {
        q.id: q
        for q in await session.scalars(select(Question).where(Question.id.in_(list(answers))))
    }
    rows = []
    for qid, answer in answers.items():
        _validate_answer(
            questions[qid], answer, attempt.layout.get("options", {}).get(str(qid), [])
        )
        rows.append(
            {
                "id": uuid.uuid4(),
                "attempt_id": attempt.id,
                "question_id": qid,
                "response": answer.as_response(),
            }
        )
    stmt = insert(AttemptAnswer).values(rows)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["attempt_id", "question_id"],
            set_={"response": stmt.excluded.response, "updated_at": func.now()},
        )
    )


async def save_answer(
    session: AsyncSession,
    user: User,
    attempt_id: uuid.UUID,
    question_id: uuid.UUID,
    answer: AnswerIn,
) -> datetime:
    attempt = await _get_own_attempt(session, user, attempt_id)
    _ensure_open(attempt)
    if _is_expired(attempt, _now()):
        await _finalize(session, attempt, status=AttemptStatus.EXPIRED)
        await session.commit()
        raise ConflictError("El tiempo de la evaluación terminó", code="attempt_expired")
    await _upsert_answers(session, attempt, {question_id: answer})
    await session.commit()
    return _now()


async def record_events(
    session: AsyncSession, user: User, attempt_id: uuid.UUID, payload: IntegrityEventsIn
) -> int:
    attempt = await _get_own_attempt(session, user, attempt_id)
    _ensure_open(attempt)
    session.add_all(
        AttemptEvent(
            attempt_id=attempt.id,
            type=e.type,
            occurred_at=e.occurred_at,
            question_id=e.question_id,
        )
        for e in payload.events
    )
    attempt.integrity_flags += len(payload.events)
    await session.commit()
    return attempt.integrity_flags


def _ensure_open(attempt: Attempt) -> None:
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise ConflictError("Este intento ya fue enviado", code="attempt_closed")


async def submit(
    session: AsyncSession, user: User, attempt_id: uuid.UUID, payload: SubmitIn
) -> Attempt:
    # FOR UPDATE: dos envíos simultáneos se serializan; el segundo ve el intento ya cerrado.
    attempt = await _get_own_attempt(session, user, attempt_id, lock=True)
    if attempt.status != AttemptStatus.IN_PROGRESS:
        return attempt  # idempotente: reenviar devuelve el mismo resultado

    if _is_expired(attempt, _now()):
        # Fuera de tiempo: se califica solo lo que se guardó a tiempo.
        await _finalize(session, attempt, status=AttemptStatus.EXPIRED)
    else:
        await _upsert_answers(session, attempt, payload.answers)
        await _finalize(session, attempt, status=AttemptStatus.SUBMITTED)
    await session.commit()
    return attempt


async def _finalize(session: AsyncSession, attempt: Attempt, *, status: AttemptStatus) -> None:
    """Califica en el servidor y congela el resultado en el intento."""
    await session.flush()
    questions = await _load_questions(session, attempt)
    answers = {a.question_id: a for a in await _saved_answers(session, attempt.id)}
    points = attempt.layout.get("points", {})

    result = grade(
        GradableItem(
            question_id=str(q.id),
            skill_code=q.skill_code,
            level_code=q.level_code,
            response_format=q.response_format,
            answer_key=q.answer_key,
            response=answers[q.id].response if q.id in answers else None,
            points=points.get(str(q.id), 1),
        )
        for q in questions
    )
    level_ranks = dict((await session.execute(select(Level.code, Level.rank))).all())

    for qid, answer in answers.items():
        answer.is_correct = result.per_question.get(str(qid), False)

    attempt.status = status
    attempt.submitted_at = _now()
    attempt.score_pct = result.score_pct
    attempt.correct_count = result.correct_count
    attempt.incorrect_count = result.incorrect_count
    attempt.suggested_level_code = suggest_level(result.by_level, level_ranks)
    attempt.skill_breakdown = {
        code: {"correct": t.correct, "total": t.total, "pct": t.pct}
        for code, t in result.by_skill.items()
    } | {"_meta": {"unanswered": result.unanswered_count}}


# ---------------------------------------------------------------------------
# Resultado y revisión (solo después de enviar)
# ---------------------------------------------------------------------------


def _correct_answer_text(question: Question) -> str:
    if question.response_format == ResponseFormat.CHOICE:
        by_id = {o["id"]: o["text"] for o in question.options or []}
        return by_id[question.answer_key["option_id"]]
    return " / ".join(question.answer_key["accepted"])


async def get_result(session: AsyncSession, user: User, attempt_id: uuid.UUID) -> AttemptResultOut:
    attempt = await get_attempt(session, user, attempt_id)
    if attempt.status == AttemptStatus.IN_PROGRESS:
        raise ConflictError(
            "El resultado estará disponible cuando envíes la evaluación", code="attempt_open"
        )

    assessment = await session.get(Assessment, attempt.assessment_id)
    questions = await _load_questions(session, attempt)
    answers = {a.question_id: a for a in await _saved_answers(session, attempt.id)}
    review = []
    for q_out, q in zip(_questions_out(attempt, questions), questions, strict=True):
        answer = answers.get(q.id)
        review.append(
            ReviewItemOut(
                question=q_out,
                response=answer.response if answer else None,
                is_correct=bool(answer and answer.is_correct),
                correct_answer=_correct_answer_text(q),
                explanation=q.explanation,
                transcript=q.stimulus.content
                if q.stimulus and q.stimulus.kind == StimulusKind.AUDIO
                else None,
            )
        )
    return AttemptResultOut(
        id=attempt.id,
        assessment_title=assessment.title,
        result=await _result_out(session, attempt),
        review=review,
    )
