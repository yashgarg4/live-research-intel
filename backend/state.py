"""Shared LangGraph state definition — extracted to avoid circular imports
between graph.py and the agent modules."""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class ResearchState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    question: str
    memory_context: str   # full retrieved memory bundle — Synthesizer uses this
    recent_memory: str    # just the single most-recent memory — Searcher uses
                          # this for pronoun resolution
    resolved_question: str  # post-rewrite standalone form of `question`
                            # (equals `question` when no rewrite happened)
    user_refinement: str    # optional mid-run steer from the browser, injected
                            # after Searcher. Empty string = user chose "skip".
    search_results: str
    sources: list[dict[str, Any]]
    critique: str
    final_answer: str
    confidence: int
    citations: list[dict[str, Any]]
