"""Anti-trampa: variantes por intento, espera entre intentos y señales que calcula el servidor."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.models import Assessment, AttemptAnswer, AttemptEvent
from tests.conftest import SLUG
from tests.test_attempts_api import correct_answers, start


async def _cooldown(minutes: int):
    async with SessionLocal() as session, session.begin():
        await session.execute(
            update(Assessment).where(Assessment.slug == SLUG).values(cooldown_minutes=minutes)
        )


async def test_retake_gets_questions_not_seen_before(student):
    seen: list[set[str]] = []
    for _ in range(3):
        attempt = await start(student)
        seen.append({q["id"] for q in attempt["questions"]})
        await student.post(f"/attempts/{attempt['id']}/submit", json={"answers": {}})
    # 3 variantes por posición: tres intentos seguidos nunca repiten una pregunta.
    assert all(len(s) == 13 for s in seen)
    assert not (seen[0] & seen[1] or seen[0] & seen[2] or seen[1] & seen[2])


async def test_cooldown_blocks_immediate_retake(student):
    # El seed no trae espera (demo); la regla sigue disponible por evaluación.
    await _cooldown(10)
    try:
        attempt = await start(student)
        await student.post(f"/attempts/{attempt['id']}/submit", json={"answers": {}})

        response = await student.post(f"/assessments/{SLUG}/attempts")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "cooldown_active"
        summary = (await student.get("/assessments")).json()[0]
        assert summary["available_at"] and summary["question_count"] == 13
    finally:
        await _cooldown(0)


async def test_client_cannot_report_server_only_signals(student):
    attempt = await start(student)
    event = {"type": "rapid_answer", "occurred_at": datetime.now(UTC).isoformat()}
    response = await student.post(f"/attempts/{attempt['id']}/events", json={"events": [event]})
    assert response.status_code == 422


async def _backdate(attempt_id: str, created: dict[str, datetime]) -> None:
    async with SessionLocal() as session, session.begin():
        for qid, at in created.items():
            await session.execute(
                update(AttemptAnswer)
                .where(
                    AttemptAnswer.attempt_id == uuid.UUID(attempt_id),
                    AttemptAnswer.question_id == uuid.UUID(qid),
                )
                .values(created_at=at, updated_at=at)
            )


async def _signals(attempt_id: str) -> list[str]:
    async with SessionLocal() as session:
        return list(
            await session.scalars(
                select(AttemptEvent.type).where(
                    AttemptEvent.attempt_id == uuid.UUID(attempt_id),
                    AttemptEvent.type.in_(["rapid_answer", "answered_after_leaving"]),
                )
            )
        )


async def test_rapid_answers_are_flagged_but_batched_sync_is_not(student):
    attempt = await start(student)
    answers = await correct_answers(attempt)
    qids = list(answers)[:6]
    for qid in qids:
        await student.put(f"/attempts/{attempt['id']}/answers/{qid}", json=answers[qid])
    t0 = datetime.now(UTC) - timedelta(minutes=5)
    await _backdate(
        attempt["id"],
        {
            qids[0]: t0,
            qids[1]: t0 + timedelta(seconds=40),  # ritmo normal
            qids[2]: t0 + timedelta(seconds=41),  # 1 s: rápida
            qids[3]: t0 + timedelta(seconds=42),  # 1 s: rápida
            qids[4]: t0 + timedelta(seconds=42.1),  # 0.1 s: sincronización en lote, no persona
            qids[5]: t0 + timedelta(seconds=90),
        },
    )
    await student.post(f"/attempts/{attempt['id']}/submit", json={"answers": {}})
    assert (await _signals(attempt["id"])).count("rapid_answer") == 2


async def test_answer_changed_after_leaving_the_tab_is_flagged(student):
    attempt = await start(student)
    answers = await correct_answers(attempt)
    qid = next(iter(answers))
    left = {"type": "tab_hidden", "occurred_at": datetime.now(UTC).isoformat(), "question_id": qid}
    await student.post(f"/attempts/{attempt['id']}/events", json={"events": [left]})
    await student.put(f"/attempts/{attempt['id']}/answers/{qid}", json=answers[qid])

    # La salida fue hace 2 min y la respuesta llegó 1 min después, ya de vuelta.
    now = datetime.now(UTC)
    async with SessionLocal() as session, session.begin():
        await session.execute(
            update(AttemptEvent)
            .where(AttemptEvent.attempt_id == uuid.UUID(attempt["id"]))
            .values(payload={"received_at": (now - timedelta(minutes=2)).isoformat()})
        )
    await _backdate(attempt["id"], {qid: now - timedelta(minutes=1)})

    await student.post(f"/attempts/{attempt['id']}/submit", json={"answers": {}})
    assert await _signals(attempt["id"]) == ["answered_after_leaving"]
