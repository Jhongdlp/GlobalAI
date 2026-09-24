import pytest

from app.domain.scoring import GradableItem, Tally, grade, is_correct, normalize_text, suggest_level

RANKS = {"PRE_A1": 0, "A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5}


def item(qid, skill, level, ok: bool | None, fmt="choice", points=1):
    """ok=True -> respuesta correcta, False -> incorrecta, None -> sin responder."""
    if fmt == "choice":
        key = {"option_id": "a"}
        response = None if ok is None else {"option_id": "a" if ok else "b"}
    else:
        key = {"accepted": ["since"]}
        response = None if ok is None else {"text": "since" if ok else "for"}
    return GradableItem(qid, skill, level, fmt, key, response, points)


class TestNormalizeText:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("  Since. ", "since"),
            ("TURN   OFF", "turn off"),
            ("Don’t!", "don't"),
            ("\tswitch off?\n", "switch off"),
        ],
    )
    def test_normalizes(self, raw, expected):
        assert normalize_text(raw) == expected


class TestIsCorrect:
    def test_choice(self):
        assert is_correct("choice", {"option_id": "b"}, {"option_id": "b"})
        assert not is_correct("choice", {"option_id": "b"}, {"option_id": "a"})

    def test_text_accepts_any_listed_variant(self):
        key = {"accepted": ["turn off", "switch off"]}
        assert is_correct("text", key, {"text": "Switch Off."})
        assert not is_correct("text", key, {"text": "turn on"})

    def test_empty_text_is_never_correct(self):
        assert not is_correct("text", {"accepted": [""]}, {"text": "   "})

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError):
            is_correct("audio", {}, {})


class TestGrade:
    def test_global_and_per_skill(self):
        result = grade(
            [
                item("1", "grammar", "A1", True),
                item("2", "grammar", "A2", True),
                item("3", "grammar", "B1", False),
                item("4", "vocabulary", "A2", True, fmt="text"),
                item("5", "reading", "B1", None),
            ]
        )
        assert result.score_pct == 60.0
        assert (result.correct_count, result.incorrect_count, result.unanswered_count) == (3, 2, 1)
        assert result.by_skill["grammar"].pct == 66.67
        assert result.by_skill["vocabulary"].pct == 100.0
        assert result.by_skill["reading"].pct == 0.0
        assert result.per_question == {"1": True, "2": True, "3": False, "4": True, "5": False}

    def test_weighted_points(self):
        result = grade(
            [
                item("1", "grammar", "A1", True, points=1),
                item("2", "grammar", "B2", False, points=3),
            ]
        )
        assert result.score_pct == 25.0

    def test_empty_assessment_scores_zero(self):
        assert grade([]).score_pct == 0.0


class TestSuggestLevel:
    def levels(self, **tallies: tuple[int, int]) -> dict[str, Tally]:
        return {
            code: Tally(correct=c, total=t, points=c, max_points=t)
            for code, (c, t) in tallies.items()
        }

    def test_all_correct_reaches_highest_tested(self):
        assert suggest_level(self.levels(A1=(1, 1), A2=(3, 3), B1=(3, 3), B2=(3, 3)), RANKS) == "B2"

    def test_single_slip_in_a1_does_not_sink_strong_student(self):
        assert suggest_level(self.levels(A1=(0, 1), A2=(3, 3), B1=(3, 3), B2=(2, 3)), RANKS) == "B2"

    def test_stops_where_student_fails(self):
        assert suggest_level(self.levels(A1=(1, 1), A2=(3, 3), B1=(1, 3), B2=(0, 3)), RANKS) == "A2"

    def test_cannot_skip_levels_with_lucky_hard_answers(self):
        # Acierta 2/3 en B2 pero falla la base: el acumulado no alcanza.
        assert (
            suggest_level(self.levels(A1=(0, 1), A2=(0, 3), B1=(1, 3), B2=(2, 3)), RANKS)
            == "PRE_A1"
        )

    def test_everything_wrong_is_level_below_lowest_tested(self):
        assert suggest_level(self.levels(A1=(0, 1), A2=(0, 3)), RANKS) == "PRE_A1"

    def test_no_levels_raises(self):
        with pytest.raises(ValueError):
            suggest_level({}, RANKS)
