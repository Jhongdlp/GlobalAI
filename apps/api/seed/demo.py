"""Grupo demo para el panel del profesor: estudiantes con intentos ya enviados.

Los intentos pasan por el mismo motor de calificación que usa la API (`_finalize`), así que
los puntajes, niveles y habilidades son reales, no números inventados. Cada perfil ejercita
una alerta distinta (integridad, caída de puntaje, apuro, tiempo agotado, puntaje bajo).
Idempotente: un estudiante que ya tiene intentos no se toca.
"""

import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import hash_password
from app.models import (
    Assessment,
    Attempt,
    AttemptAnswer,
    AttemptEvent,
    AttemptStatus,
    Question,
    ResponseFormat,
    Role,
    User,
)
from app.services.attempt_service import _build_layout, _finalize

PASSWORD = "Demo1234!"

# (nombre, email, intentos del más antiguo al más reciente)
# intento = (acierto 0–1, hace_días, minutos, eventos de integridad, expiró)
GROUP = [
    (
        "Mateo Andrade",
        "mateo@globalai.demo",
        [(0.4, 20, 18, {}, False), (0.6, 9, 16, {}, False), (0.8, 1, 15, {}, False)],
    ),
    (
        "Valentina Paredes",
        "valentina@globalai.demo",
        [
            (0.8, 12, 17, {}, False),
            (
                0.95,
                2,
                12,
                {"tab_hidden": 4, "answered_after_leaving": 3, "paste": 2, "window_blur": 1},
                False,
            ),
        ],
    ),
    ("Sebastián Mora", "sebastian@globalai.demo", [(0.25, 3, 22, {"window_blur": 1}, False)]),
    (
        "Camila Herrera",
        "camila@globalai.demo",
        [(0.9, 15, 19, {}, False), (0.4, 1, 14, {}, False)],
    ),
    (
        "Diego Salazar",
        "diego@globalai.demo",
        [(0.9, 0, 3, {"paste": 3, "rapid_answer": 5}, False)],
    ),
    ("Isabella Vega", "isabella@globalai.demo", [(0.6, 4, 25, {"tab_hidden": 1}, True)]),
    ("Sofía Castillo", "sofia@globalai.demo", [(0.9, 25, 20, {}, False), (1.0, 6, 17, {}, False)]),
    ("Nicolás Ortiz", "nicolas@globalai.demo", []),
]

WRONG_TEXT = "i dont know"


def _response(q: Question, correct: bool, rng: random.Random) -> dict:
    if q.response_format == ResponseFormat.CHOICE:
        right = q.answer_key["option_id"]
        wrong = [o["id"] for o in q.options if o["id"] != right]
        return {"option_id": right if correct else rng.choice(wrong)}
    if q.response_format == ResponseFormat.SPEECH:
        text = q.answer_key.get("target") or "Last weekend I visited my family and we cooked."
        return {"transcript": text, "score": 0.9 if correct else 0.3, "tries": 1}
    return {"text": q.answer_key["accepted"][0] if correct else WRONG_TEXT}


async def seed_demo_group(session: AsyncSession, slug: str) -> int:
    assessment = await session.scalar(
        select(Assessment).options(selectinload(Assessment.items)).where(Assessment.slug == slug)
    )
    questions = {
        q.id: q
        for q in await session.scalars(
            select(Question).where(Question.id.in_([i.question_id for i in assessment.items]))
        )
    }
    await session.execute(
        insert(User)
        .values(
            [
                {
                    "email": email,
                    "password_hash": hash_password(PASSWORD),
                    "full_name": name,
                    "role": Role.STUDENT,
                }
                for name, email, _ in GROUP
            ]
        )
        .on_conflict_do_nothing(index_elements=["email"])
    )

    now = datetime.now(UTC)
    created = 0
    for _, email, attempts in GROUP:
        user = await session.scalar(select(User).where(User.email == email))
        if await session.scalar(select(Attempt.id).where(Attempt.user_id == user.id).limit(1)):
            continue
        rng = random.Random(email)  # determinista: el mismo grupo en cada máquina
        for accuracy, days_ago, minutes, events, expired in attempts:
            submitted = now - timedelta(days=days_ago, hours=rng.randint(1, 8))
            started = submitted - timedelta(minutes=minutes, seconds=rng.randint(0, 59))
            attempt = Attempt(
                user_id=user.id,
                assessment_id=assessment.id,
                status=AttemptStatus.IN_PROGRESS,
                started_at=started,
                expires_at=started + timedelta(minutes=assessment.time_limit_minutes or 25),
                layout=_build_layout(assessment, questions),
                integrity_flags=sum(events.values()),
            )
            session.add(attempt)
            await session.flush()
            session.add_all(
                AttemptAnswer(
                    attempt_id=attempt.id,
                    question_id=q.id,
                    response=_response(q, rng.random() < accuracy, rng),
                )
                for q in (questions[uuid.UUID(qid)] for qid in attempt.layout["questions"])
                if not (expired and rng.random() < 0.3)  # sin tiempo: algunas sin responder
            )
            order = attempt.layout["questions"]
            session.add_all(
                AttemptEvent(
                    attempt_id=attempt.id,
                    type=kind,
                    occurred_at=started + timedelta(seconds=rng.randint(30, minutes * 60)),
                    question_id=rng.choice(order),
                )
                for kind, n in events.items()
                for _ in range(n)
            )
            await _finalize(
                session,
                attempt,
                status=AttemptStatus.EXPIRED if expired else AttemptStatus.SUBMITTED,
            )
            attempt.submitted_at = submitted
            created += 1
    return created
