from app.domain.practice import said_right
from app.services import speech
from tests.test_speaking import spoken


def test_word_must_be_heard_clearly():
    assert said_right("think", spoken("Think."))
    assert not said_right("think", spoken("sink"))
    assert not said_right("think", spoken("think", logprob=-2.0))  # el reconocedor dudó


def stt(text: str):
    async def fake(*_):
        return {
            "text": text,
            "words": [
                {"text": w, "type": "word", "start": 0, "end": 0.3, "logprob": -0.05}
                for w in text.split()
            ],
        }

    return fake


async def test_listen_judges_the_lesson_word(student, monkeypatch):
    lesson = (await student.get("/practice/lesson")).json()
    for said, ok in ((lesson["word"], True), ("banana", False)):
        monkeypatch.setattr(speech, "transcribe", stt(said))
        r = await student.post(
            f"/practice/listen?lesson={lesson['id']}",
            content=b"x",
            headers={"Content-Type": "audio/webm"},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"text": said, "ok": ok, "unclear": []}


async def test_chat_closes_after_max_turns(student):
    first = await student.post("/practice/reply", json={"turns": ["Q?", "I like pizza"]})
    last = await student.post("/practice/reply", json={"turns": ["Q?", "a", "b?", "c"]})
    assert (first.json()["done"], last.json()["done"]) == (False, True)
    too_long = await student.post("/practice/reply", json={"turns": ["a"] * 6})
    assert too_long.status_code == 422


def test_chat_correction_is_parsed_and_bounded():
    from app.services.speech import parse_chat

    raw = 'ok {"fix": "Titanic is very romantic.", "why": "Falta el sujeto: it.", "reply": "Nice!"}'
    assert parse_chat(raw) == {
        "reply": "Nice!",
        "fix": "Titanic is very romantic.",
        "why": "Falta el sujeto: it.",
    }
    assert parse_chat('{"fix": null, "why": "x", "reply": "Hi"}')["why"] is None
    assert parse_chat("no json") is None
