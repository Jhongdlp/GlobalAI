import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.models import Attempt, Question
from tests.conftest import SLUG


async def start(client) -> dict:
    response = await client.post(f"/assessments/{SLUG}/attempts")
    assert response.status_code == 200, response.text
    return response.json()


async def correct_answers(attempt: dict) -> dict[str, dict]:
    """Construye respuestas correctas leyendo la BD (el cliente real nunca puede hacer esto)."""
    ids = [uuid.UUID(q["id"]) for q in attempt["questions"]]
    async with SessionLocal() as session:
        questions = await session.scalars(select(Question).where(Question.id.in_(ids)))
        return {
            str(q.id): {"option_id": q.answer_key["option_id"]}
            if q.response_format == "choice"
            else {"text": q.answer_key["accepted"][0]}
            for q in questions
        }


async def test_requires_authentication(anon):
    response = await anon.post(f"/assessments/{SLUG}/attempts")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_attempt_payload_never_exposes_answers(student):
    attempt = await start(student)
    raw = json.dumps(attempt)

    assert len(attempt["questions"]) == 10
    for forbidden in ("answer_key", "explanation", "accepted", "Mark from Blue Sky Travel"):
        assert forbidden not in raw
    listening = next(q for q in attempt["questions"] if q["skill"] == "listening")
    assert listening["stimulus"]["content"] is None
    assert listening["stimulus"]["audio_url"]


async def test_perfect_submission_is_graded_on_server(student):
    attempt = await start(student)
    answers = await correct_answers(attempt)

    response = await student.post(f"/attempts/{attempt['id']}/submit", json={"answers": answers})

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["score_pct"] == 100.0
    assert result["correct_count"] == 10
    assert result["suggested_level"]["code"] == "B2"
    assert {s["code"] for s in result["skills"]} == {
        "grammar",
        "vocabulary",
        "reading",
        "listening",
    }


async def test_client_cannot_inject_its_own_score(student):
    attempt = await start(student)

    response = await student.post(
        f"/attempts/{attempt['id']}/submit",
        json={"answers": {}, "score_pct": 100, "correct_count": 10},
    )

    result = response.json()["result"]
    assert result["score_pct"] == 0.0
    assert result["unanswered_count"] == 10


async def test_resume_keeps_same_attempt_and_saved_answers(student):
    attempt = await start(student)
    question = attempt["questions"][0]
    answer = (
        {"option_id": question["options"][0]["id"]} if question["options"] else {"text": "since"}
    )
    saved = await student.put(f"/attempts/{attempt['id']}/answers/{question['id']}", json=answer)
    assert saved.status_code == 200

    resumed = await start(student)

    assert resumed["id"] == attempt["id"]
    assert [q["id"] for q in resumed["questions"]] == [q["id"] for q in attempt["questions"]]
    assert resumed["answers"] == {question["id"]: answer}


async def test_rejects_answer_for_question_outside_attempt(student):
    attempt = await start(student)
    response = await student.put(
        f"/attempts/{attempt['id']}/answers/{uuid.uuid4()}", json={"text": "hack"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_question"


async def test_submit_is_idempotent_and_closes_attempt(student):
    attempt = await start(student)
    answers = await correct_answers(attempt)
    first = await student.post(f"/attempts/{attempt['id']}/submit", json={"answers": answers})

    # Un segundo envío (p. ej. reintento tras un corte) no recalifica ni cambia nada.
    second = await student.post(f"/attempts/{attempt['id']}/submit", json={"answers": {}})
    assert second.json()["result"] == first.json()["result"]

    qid = attempt["questions"][0]["id"]
    late = await student.put(f"/attempts/{attempt['id']}/answers/{qid}", json={"text": "x"})
    assert late.status_code == 409
    assert late.json()["error"]["code"] == "attempt_closed"


async def test_expired_attempt_rejects_answers_and_is_auto_graded(student):
    attempt = await start(student)
    async with SessionLocal() as session, session.begin():
        await session.execute(
            update(Attempt)
            .where(Attempt.id == uuid.UUID(attempt["id"]))
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=5))
        )

    qid = attempt["questions"][0]["id"]
    response = await student.put(f"/attempts/{attempt['id']}/answers/{qid}", json={"text": "x"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "attempt_expired"
    view = (await student.get(f"/attempts/{attempt['id']}")).json()
    assert view["status"] == "expired"
    assert view["result"]["score_pct"] == 0.0


async def test_result_is_hidden_until_submitted(student):
    attempt = await start(student)
    response = await student.get(f"/attempts/{attempt['id']}/result")
    assert response.status_code == 409


async def test_other_users_cannot_see_attempt(student, teacher):
    attempt = await start(student)
    response = await teacher.get(f"/attempts/{attempt['id']}")
    assert response.status_code == 404


async def test_teacher_route_is_role_protected(student, teacher):
    assert (await student.get("/teacher/attempts")).status_code == 403
    assert (await teacher.get("/teacher/attempts")).status_code == 200


async def test_integrity_events_are_counted(student):
    attempt = await start(student)
    events = [
        {"type": "tab_hidden", "occurred_at": datetime.now(UTC).isoformat()},
        {"type": "paste", "occurred_at": datetime.now(UTC).isoformat()},
    ]
    response = await student.post(f"/attempts/{attempt['id']}/events", json={"events": events})
    assert response.json() == {"integrity_flags": 2}


async def test_progress_reflects_submitted_attempts(student):
    attempt = await start(student)
    await student.post(
        f"/attempts/{attempt['id']}/submit", json={"answers": await correct_answers(attempt)}
    )

    progress = (await student.get("/me/progress")).json()

    assert progress["total_attempts"] == 1
    assert progress["best_score_pct"] == 100.0
    assert progress["current_level"]["code"] == "B2"


async def test_login_is_rate_limited(anon):
    body = {"email": "nadie@globalai.demo", "password": "wrong"}
    codes = [(await anon.post("/auth/login", json=body)).status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]


async def test_listening_audio_requires_auth_and_is_served(student, anon):
    attempt = await start(student)
    url = next(q for q in attempt["questions"] if q["skill"] == "listening")["stimulus"][
        "audio_url"
    ]
    path = url.removeprefix("/api/v1")

    assert (await anon.get(path)).status_code == 401
    response = await student.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert (await student.get(f"/stimuli/{uuid.uuid4()}/audio")).status_code == 404


async def test_coach_feedback_is_generated_once_and_persisted(student):
    attempt = await start(student)
    assert (await student.post(f"/attempts/{attempt['id']}/feedback")).status_code == 409

    await student.post(f"/attempts/{attempt['id']}/submit", json={"answers": {}})
    first = await student.post(f"/attempts/{attempt['id']}/feedback")
    assert first.status_code == 200
    assert "nivel sugerido" in first.json()["feedback"]

    again = await student.post(f"/attempts/{attempt['id']}/feedback")
    assert again.json() == first.json()
    result = (await student.get(f"/attempts/{attempt['id']}/result")).json()
    assert result["result"]["ai_feedback"] == first.json()["feedback"]
    # Sin TTS configurado la voz responde 404 controlado, no 500.
    audio = await student.get(f"/attempts/{attempt['id']}/feedback/audio")
    assert audio.json()["error"]["code"] == "tts_unavailable"
