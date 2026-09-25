import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.models import Attempt, AttemptAnswer, Question
from app.services import speech
from tests.conftest import SLUG

QUESTIONS = 13


async def start(client) -> dict:
    response = await client.post(f"/assessments/{SLUG}/attempts")
    assert response.status_code == 200, response.text
    return response.json()


async def correct_answers(attempt: dict) -> dict[str, dict]:
    """Construye respuestas correctas leyendo la BD (el cliente real nunca puede hacer esto).
    Las orales no viajan en el envío: se guardan ya calificadas (ver perfect_speech)."""
    ids = [uuid.UUID(q["id"]) for q in attempt["questions"] if q["response_format"] != "speech"]
    async with SessionLocal() as session:
        questions = await session.scalars(select(Question).where(Question.id.in_(ids)))
        return {
            str(q.id): {"option_id": q.answer_key["option_id"]}
            if q.response_format == "choice"
            else {"text": q.answer_key["accepted"][0]}
            for q in questions
        }


async def perfect_speech(attempt: dict) -> None:
    async with SessionLocal() as session, session.begin():
        session.add_all(
            AttemptAnswer(
                attempt_id=uuid.UUID(attempt["id"]),
                question_id=uuid.UUID(q["id"]),
                response={"transcript": "perfect", "score": 1.0, "tries": 1},
            )
            for q in attempt["questions"]
            if q["response_format"] == "speech"
        )


def speech_question(attempt: dict, qtype: str = "read_aloud") -> dict:
    return next(q for q in attempt["questions"] if q["type"] == qtype)


def fake_stt(text: str) -> dict:
    """Respuesta con la forma de ElevenLabs Scribe: una palabra cada 0.4 s, confianza alta."""
    words = [
        {"text": w, "type": "word", "start": i * 0.4, "end": i * 0.4 + 0.3, "logprob": -0.05}
        for i, w in enumerate(text.split())
    ]
    return {"text": text, "words": words}


async def test_requires_authentication(anon):
    response = await anon.post(f"/assessments/{SLUG}/attempts")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_attempt_payload_never_exposes_answers(student):
    attempt = await start(student)
    raw = json.dumps(attempt)

    assert len(attempt["questions"]) == QUESTIONS
    # Como claves JSON: un enunciado puede contener la palabra "explanation" legítimamente.
    for forbidden in ('"answer_key"', '"explanation"', '"accepted"', "Mark from Blue Sky Travel"):
        assert forbidden not in raw
    listening = next(q for q in attempt["questions"] if q["skill"] == "listening")
    assert listening["stimulus"]["content"] is None
    assert listening["stimulus"]["audio_url"]


async def test_perfect_submission_is_graded_on_server(student):
    attempt = await start(student)
    answers = await correct_answers(attempt)
    await perfect_speech(attempt)

    response = await student.post(f"/attempts/{attempt['id']}/submit", json={"answers": answers})

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["score_pct"] == 100.0
    assert result["correct_count"] == QUESTIONS
    assert result["suggested_level"]["code"] == "B2"
    assert {s["code"] for s in result["skills"]} == {
        "grammar",
        "vocabulary",
        "reading",
        "listening",
        "speaking",
    }


async def test_client_cannot_inject_its_own_score(student):
    attempt = await start(student)

    response = await student.post(
        f"/attempts/{attempt['id']}/submit",
        json={"answers": {}, "score_pct": 100, "correct_count": 10},
    )

    result = response.json()["result"]
    assert result["score_pct"] == 0.0
    assert result["unanswered_count"] == QUESTIONS


async def test_resume_keeps_same_attempt_and_saved_answers(student):
    attempt = await start(student)
    question = next(q for q in attempt["questions"] if q["response_format"] != "speech")
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
    await perfect_speech(attempt)
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


async def test_speech_without_stt_provider_fails_cleanly(student):
    attempt = await start(student)
    q = speech_question(attempt)
    url = f"/attempts/{attempt['id']}/answers/{q['id']}/speech"

    response = await student.put(url, content=b"fake-audio", headers={"content-type": "audio/webm"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "stt_unavailable"

    not_audio = await student.put(url, json={"text": "hi"})
    assert not_audio.json()["error"]["code"] == "invalid_audio"
    typed = await student.put(f"/attempts/{attempt['id']}/answers/{q['id']}", json={"text": "hi"})
    assert typed.json()["error"]["code"] == "invalid_answer"


async def test_read_aloud_is_graded_on_server_with_limited_tries(student, monkeypatch):
    attempt = await start(student)
    q = speech_question(attempt)
    url = f"/attempts/{attempt['id']}/answers/{q['id']}/speech"
    audio = {"content": b"fake-audio", "headers": {"content-type": "audio/webm;codecs=opus"}}

    async def silence(audio, content_type):
        return {"text": "", "words": []}

    monkeypatch.setattr(speech, "transcribe", silence)
    assert (await student.put(url, **audio)).json()["error"]["code"] == "no_speech"

    async def reads_prompt(audio, content_type):
        assert content_type == "audio/webm"
        return fake_stt(q["prompt"])

    monkeypatch.setattr(speech, "transcribe", reads_prompt)
    saved = await student.put(url, **audio)
    assert saved.status_code == 200, saved.text
    assert saved.json()["tries_left"] == 2  # el silencio no gastó una grabación

    # Antes de enviar solo se ve lo que se entendió, nunca el puntaje.
    view = await student.get(f"/attempts/{attempt['id']}")
    assert view.json()["answers"][q["id"]] == {"transcript": q["prompt"], "tries": 1}

    for _ in range(2):
        await student.put(url, **audio)
    exhausted = await student.put(url, **audio)
    assert exhausted.json()["error"]["code"] == "speech_tries_exhausted"

    result = (await student.post(f"/attempts/{attempt['id']}/submit", json={})).json()
    item = next(i for i in result["review"] if i["question"]["id"] == q["id"])
    assert item["is_correct"]
    assert item["response"]["accuracy"] == 1.0
    assert item["correct_answer"] == q["prompt"]
    speaking = next(s for s in result["result"]["skills"] if s["code"] == "speaking")
    assert speaking["correct"] == 1


async def test_overlong_password_is_rejected_not_500(anon):
    body = {"email": "otro@globalai.demo", "password": "x" * 100}
    response = await anon.post("/auth/login", json=body)
    assert response.status_code == 401


async def test_speech_upload_is_capped_while_streaming(student):
    attempt = (await student.post(f"/assessments/{SLUG}/attempts")).json()
    qid = attempt["questions"][0]["id"]

    async def chunked():  # sin Content-Length: el límite debe cortar igual
        for _ in range(6):
            yield b"\0" * (1024 * 1024)

    response = await student.put(
        f"/attempts/{attempt['id']}/answers/{qid}/speech",
        content=chunked(),
        headers={"content-type": "audio/webm"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "audio_too_large"


async def test_responses_carry_request_id_and_security_headers(anon):
    response = await anon.get("/health", headers={"x-request-id": "abc123"})
    assert response.headers["x-request-id"] == "abc123"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_listening_audio_is_not_served_to_users_without_that_attempt(student, teacher):
    attempt = await start(student)
    url = next(q for q in attempt["questions"] if q["skill"] == "listening")["stimulus"][
        "audio_url"
    ]
    # Otro usuario con sesión válida y el ID exacto: 404, como si no existiera.
    assert (await teacher.get(url.removeprefix("/api/v1"))).status_code == 404


async def test_paid_endpoints_are_rate_limited_per_user(student):
    attempt = await start(student)
    path = f"/attempts/{attempt['id']}/feedback/audio"
    codes = [(await student.get(path)).status_code for _ in range(11)]
    assert 429 not in codes[:10]
    assert codes[10] == 429


async def test_login_is_rate_limited_per_ip_across_emails(anon):
    for i in range(50):
        await anon.post("/auth/login", json={"email": f"u{i}@x.com", "password": "bad"})
    response = await anon.post("/auth/login", json={"email": "otro@x.com", "password": "bad"})
    assert response.status_code == 429
