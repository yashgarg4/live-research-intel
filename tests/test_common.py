"""Tests for ``chunk_text`` — coerces Gemini astream chunk content into a
plain string. Each agent loops over chunks ~50 times per run, so a wrong
result here would produce silently empty output or crashes."""
from __future__ import annotations

from backend.agents._common import chunk_text


class TestChunkText:
    def test_plain_string_passes_through(self):
        assert chunk_text("hello world") == "hello world"

    def test_empty_string_returns_empty(self):
        assert chunk_text("") == ""

    def test_list_of_strings_concatenates(self):
        assert chunk_text(["foo", " ", "bar"]) == "foo bar"

    def test_list_of_dicts_with_text_field(self):
        # Gemini sometimes emits content as a list of part dicts.
        assert chunk_text([{"text": "hello"}, {"text": " world"}]) == "hello world"

    def test_mixed_list_strings_and_dicts(self):
        assert chunk_text(["pre ", {"text": "mid"}, " post"]) == "pre mid post"

    def test_list_with_unknown_dict_keys_is_skipped(self):
        # Dict without a "text" key contributes nothing.
        assert chunk_text([{"foo": "bar"}, {"text": "kept"}]) == "kept"

    def test_unrecognized_type_returns_empty(self):
        # Integers, None, arbitrary objects all coerce to "".
        assert chunk_text(42) == ""
        assert chunk_text(None) == ""
        assert chunk_text(object()) == ""

    def test_dict_with_non_string_text_value_is_stringified(self):
        # Defensive: text=42 becomes "42" rather than crashing.
        assert chunk_text([{"text": 42}]) == "42"
