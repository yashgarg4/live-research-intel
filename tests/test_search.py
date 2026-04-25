"""Tests for the MCP-client side of ``backend/tools/search.py``.

Two pure functions:

* ``_coerce_outcome`` — defensive normalisation of whatever JSON came out of
  the MCP server.
* ``_parse_tool_result`` — picks structured content first, falls back to
  JSON-decoding TextContent items, falls back to an explicit error.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from backend.tools.search import _coerce_outcome, _parse_tool_result


# ─── _coerce_outcome ──────────────────────────────────────────────────────


class TestCoerceOutcome:
    def test_well_formed_payload_passes_through(self):
        payload = {
            "sources": [{"title": "T", "url": "https://x", "content": "c"}],
            "error": None,
        }
        result = _coerce_outcome(payload)
        assert result["sources"] == payload["sources"]
        assert result["error"] is None

    def test_missing_sources_yields_empty_list(self):
        result = _coerce_outcome({"error": "boom"})
        assert result["sources"] == []
        assert result["error"] == "boom"

    def test_sources_wrong_type_replaced_with_empty_list(self):
        # A misbehaving MCP server returns sources as a string — protect callers.
        result = _coerce_outcome({"sources": "not-a-list", "error": None})
        assert result["sources"] == []

    def test_error_coerced_to_string(self):
        # Defensive: integer error becomes "500".
        result = _coerce_outcome({"sources": [], "error": 500})
        assert result["error"] == "500"

    def test_empty_dict_returns_empty_outcome(self):
        result = _coerce_outcome({})
        assert result["sources"] == []
        assert result["error"] is None

    def test_null_sources_yields_empty_list(self):
        result = _coerce_outcome({"sources": None, "error": None})
        assert result["sources"] == []


# ─── _parse_tool_result ───────────────────────────────────────────────────


def _structured(payload: dict) -> SimpleNamespace:
    """A CallToolResult-shaped object that exposes ``structuredContent``."""
    return SimpleNamespace(structuredContent=payload, content=None)


def _text_content(payload: dict) -> SimpleNamespace:
    """A CallToolResult with no structured content but a JSON TextContent
    item — the fallback path the MCP SDK exercises in some versions."""
    text_item = SimpleNamespace(text=json.dumps(payload))
    return SimpleNamespace(structuredContent=None, content=[text_item])


def _bad_text_content(text: str) -> SimpleNamespace:
    text_item = SimpleNamespace(text=text)
    return SimpleNamespace(structuredContent=None, content=[text_item])


def _empty_result() -> SimpleNamespace:
    return SimpleNamespace(structuredContent=None, content=[])


class TestParseToolResult:
    def test_structured_content_is_preferred(self):
        payload = {
            "sources": [{"title": "wiki", "url": "https://w", "content": "c"}],
            "error": None,
        }
        result = _parse_tool_result(_structured(payload))
        assert len(result["sources"]) == 1
        assert result["sources"][0]["title"] == "wiki"
        assert result["error"] is None

    def test_text_content_json_fallback(self):
        payload = {
            "sources": [{"title": "tav", "url": "https://t", "content": "c"}],
            "error": None,
        }
        result = _parse_tool_result(_text_content(payload))
        assert len(result["sources"]) == 1
        assert result["sources"][0]["title"] == "tav"

    def test_text_content_with_error_field(self):
        result = _parse_tool_result(_text_content({"sources": [], "error": "429"}))
        assert result["sources"] == []
        assert result["error"] == "429"

    def test_unparseable_text_content_yields_explicit_error(self):
        result = _parse_tool_result(_bad_text_content("not json at all"))
        assert result["sources"] == []
        assert result["error"] is not None
        assert "no parseable payload" in result["error"]

    def test_empty_content_list_yields_explicit_error(self):
        result = _parse_tool_result(_empty_result())
        assert result["sources"] == []
        assert result["error"] is not None

    def test_structured_content_with_snake_case_attribute(self):
        # SDK alternate field name.
        ns = SimpleNamespace(
            structured_content={"sources": [], "error": "fallback path"},
            content=None,
        )
        # _parse_tool_result also probes ``structured_content`` (snake_case).
        result = _parse_tool_result(ns)
        assert result["error"] == "fallback path"
