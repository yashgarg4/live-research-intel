"""Pure-function tests for backend.agents.searcher helpers.

We test the two non-async helpers that drive critical behaviour:

* ``_needs_memory_rewrite`` — gates the per-call LLM rewrite. False positives
  here cost free-tier RPM; false negatives cause pronoun follow-ups to miss
  their prior subject.
* ``_build_fallback_note`` — surfaces partial-failure UX. Wrong copy here
  silently confuses the user when one MCP source dies.

No LLM, no network, no subprocess. Pure logic.
"""
from __future__ import annotations

from backend.agents.searcher import _build_fallback_note, _needs_memory_rewrite


# ─── _needs_memory_rewrite ────────────────────────────────────────────────


class TestNeedsMemoryRewrite:
    def test_pronoun_it_triggers_rewrite(self):
        assert _needs_memory_rewrite("How does it work?") is True

    def test_pronoun_this_triggers_rewrite(self):
        assert _needs_memory_rewrite("explain this in detail") is True

    def test_pronoun_them_triggers_rewrite(self):
        assert _needs_memory_rewrite("compare them on latency") is True

    def test_followup_starter_so_triggers(self):
        assert _needs_memory_rewrite("so what about caching") is True

    def test_followup_starter_and_triggers(self):
        assert _needs_memory_rewrite("and tell me more") is True

    def test_short_question_triggers(self):
        # Three words — likely context-dependent even without pronouns.
        assert _needs_memory_rewrite("Apache Kafka use") is True

    def test_self_contained_question_does_not_trigger(self):
        # 7+ words, no pronouns, no follow-up starter — safe to skip rewrite.
        assert (
            _needs_memory_rewrite(
                "Explain the Kubernetes scheduler architecture from start to finish"
            )
            is False
        )

    def test_self_contained_long_question_does_not_trigger(self):
        assert (
            _needs_memory_rewrite(
                "What are the differences between Postgres and MySQL replication"
            )
            is False
        )

    def test_empty_string_does_not_trigger(self):
        assert _needs_memory_rewrite("") is False

    def test_whitespace_only_does_not_trigger(self):
        assert _needs_memory_rewrite("   ") is False

    def test_pronoun_inside_compound_word_is_not_a_match(self):
        # "items" contains the substring "it" but \b boundaries should reject it.
        assert _needs_memory_rewrite("List Kubernetes items in the cluster") is False


# ─── _build_fallback_note ─────────────────────────────────────────────────

# Minimal outcome builders for clarity in test bodies.
def _ok(n: int) -> dict:
    return {"sources": [{"title": f"s{i}"} for i in range(n)], "error": None}


def _fail(msg: str) -> dict:
    return {"sources": [], "error": msg}


def _empty() -> dict:
    return {"sources": [], "error": None}


class TestBuildFallbackNote:
    def test_both_succeed_with_results_returns_empty(self):
        assert _build_fallback_note(_ok(5), _ok(3)) == ""

    def test_both_fail_emits_all_sources_unavailable(self):
        note = _build_fallback_note(_fail("429 quota"), _fail("HTTPError"))
        assert "All sources unavailable" in note
        assert "429 quota" in note
        assert "HTTPError" in note
        assert "model knowledge only" in note

    def test_tavily_fails_wiki_succeeds_emits_partial(self):
        note = _build_fallback_note(_fail("SSL error"), _ok(3))
        assert "Partial sources only" in note
        assert "Web search failed" in note
        assert "SSL error" in note
        # Wiki is fine; should not be mentioned in failure list.
        assert "Wikipedia failed" not in note

    def test_wiki_fails_tavily_succeeds_emits_partial(self):
        note = _build_fallback_note(_ok(5), _fail("HTTPStatusError 503"))
        assert "Partial sources only" in note
        assert "Wikipedia failed" in note
        assert "HTTPStatusError 503" in note
        assert "Web search failed" not in note

    def test_tavily_fails_wiki_empty_emits_web_only_unavailable(self):
        # total=0 path, only Tavily errored.
        note = _build_fallback_note(_fail("network"), _empty())
        assert "Web search unavailable" in note
        assert "Wikipedia returned nothing" in note
        assert "model knowledge only" in note

    def test_wiki_fails_tavily_empty_emits_wiki_only_unavailable(self):
        note = _build_fallback_note(_empty(), _fail("timeout"))
        assert "Wikipedia unavailable" in note
        assert "web search returned nothing" in note

    def test_both_empty_no_errors_emits_no_results_found(self):
        note = _build_fallback_note(_empty(), _empty())
        assert "No results found across web or Wikipedia" in note
        assert "model knowledge only" in note

    def test_tavily_succeeds_wiki_empty_emits_partial_with_wiki_no_results(self):
        note = _build_fallback_note(_ok(5), _empty())
        assert "Partial sources only" in note
        assert "Wikipedia returned no results" in note
        assert "Web search" not in note  # Tavily is fine

    def test_tavily_empty_wiki_succeeds_emits_partial_with_web_no_results(self):
        note = _build_fallback_note(_empty(), _ok(3))
        assert "Partial sources only" in note
        assert "Web search returned no results" in note
        assert "Wikipedia" not in note  # Wiki is fine
