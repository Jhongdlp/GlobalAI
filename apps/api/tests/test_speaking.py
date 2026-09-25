from app.domain.scoring import GradableItem, grade
from app.domain.speaking import (
    Word,
    fluency,
    parse_rubric,
    score_open_response,
    score_read_aloud,
    words_from_stt,
)

TARGET = "I usually take the bus to work."


def spoken(text: str, gap: float = 0.1, logprob: float = -0.05) -> list[Word]:
    words, t = [], 0.0
    for w in text.split():
        words.append(Word(w, t, t + 0.3, logprob))
        t += 0.3 + gap
    return words


def test_reads_only_words_from_scribe_payload():
    payload = {
        "words": [
            {"text": "Hi", "type": "word", "start": 0, "end": 0.2, "logprob": -0.1},
            {"text": " ", "type": "spacing"},
            {"text": "(laughter)", "type": "audio_event"},
        ]
    }
    assert [w.text for w in words_from_stt(payload)] == ["Hi"]


def test_perfect_reading_passes_and_lists_nothing_missed():
    result = score_read_aloud(TARGET, spoken("I usually take the bus to work."))
    assert result["accuracy"] == 1.0
    assert result["missed"] == []
    assert result["score"] > 0.9


def test_missed_words_lower_accuracy_and_are_reported():
    result = score_read_aloud(TARGET, spoken("I take the bus work"))
    assert result["missed"] == ["usually", "to"]
    assert result["accuracy"] == round(5 / 7, 3)


def test_fluent_but_wrong_text_scores_near_zero():
    assert score_read_aloud(TARGET, spoken("hello my name is laura"))["score"] < 0.15


def test_long_pauses_and_low_confidence_cost_points():
    clean = score_read_aloud(TARGET, spoken(TARGET))
    halting = score_read_aloud(TARGET, spoken(TARGET, gap=1.5, logprob=-1.5))
    assert halting["long_pauses"] == 6
    assert halting["score"] < clean["score"] - 0.2


def test_fluency_needs_at_least_two_words():
    assert fluency(spoken("hi")) == (0.0, 0.0, 0)


def test_rubric_parsing_is_defensive():
    raw = 'Claro: {"task": 4, "grammar": 9, "vocabulary": "2", "feedback": "Usa \'went\'."}'
    assert parse_rubric(raw) == {
        "task": 4,
        "grammar": 4,
        "vocabulary": 2,
        "feedback": "Usa 'went'.",
    }
    assert parse_rubric("no json") is None
    assert parse_rubric('{"task": 3}') is None


def test_open_response_uses_rubric_or_capped_heuristic():
    words = spoken("I went to the beach with my family " * 5)
    rubric = {"task": 4, "grammar": 3, "vocabulary": 3, "feedback": None}
    assert score_open_response(words, rubric, 35)["graded_by"] == "ai"
    heuristic = score_open_response(words, None, 35)
    assert heuristic["graded_by"] == "heuristic"
    assert heuristic["score"] <= 0.75


def test_speech_gives_partial_credit_in_grade():
    items = [
        GradableItem("1", "speaking", "A2", "speech", {}, {"score": 0.8}),
        GradableItem("2", "speaking", "B1", "speech", {}, {"score": 0.4}),
    ]
    result = grade(items)
    assert result.score_pct == 60.0
    assert result.per_question == {"1": True, "2": False}
    assert result.by_skill["speaking"].correct == 1
