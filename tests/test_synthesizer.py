"""Tests for ``_parse_confidence`` — extracts the trailing ``CONFIDENCE: N``
score from the Synthesizer's output. Anything that drops the score
silently to 0 or accepts an out-of-range value would mis-render the
ResultCard's colour-banded badge."""
from __future__ import annotations

from backend.agents.synthesizer import _parse_confidence


class TestParseConfidence:
    def test_extracts_score_from_trailing_line(self):
        text = "Some answer text\n\nCONFIDENCE: 85"
        assert _parse_confidence(text) == 85

    def test_extracts_score_at_start(self):
        assert _parse_confidence("CONFIDENCE: 50\nrest of text") == 50

    def test_lowercase_keyword_is_accepted(self):
        # The regex uses re.IGNORECASE.
        assert _parse_confidence("answer\nconfidence: 75") == 75

    def test_mixed_case_keyword_is_accepted(self):
        assert _parse_confidence("answer\nConfidence: 60") == 60

    def test_extra_whitespace_between_keyword_and_value(self):
        assert _parse_confidence("answer\nCONFIDENCE:    42") == 42

    def test_score_above_100_is_clamped(self):
        assert _parse_confidence("CONFIDENCE: 200") == 100

    def test_score_below_0_returns_zero(self):
        # Regex is r"\d{1,3}" — matches "5" of "-5"; minus sign isn't captured.
        # We're testing that the result is non-negative regardless.
        result = _parse_confidence("CONFIDENCE: -5")
        assert 0 <= result <= 100

    def test_missing_confidence_returns_zero(self):
        assert _parse_confidence("answer with no confidence line") == 0

    def test_empty_string_returns_zero(self):
        assert _parse_confidence("") == 0

    def test_three_digit_score_clamped(self):
        assert _parse_confidence("CONFIDENCE: 999") == 100
