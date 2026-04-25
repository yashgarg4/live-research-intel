"""Searcher agent — runs Tavily search then streams a Gemini summary."""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any

from ag_ui.core import (
    EventType,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.config import get_stream_writer

from backend.agents._common import chunk_text, stream_llm_with_retry
from backend.config import get_llm
from backend.state import ResearchState
from backend.tools.search import tavily_search

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a research agent. Search the web for information about the "
    "given query. Summarize the key findings clearly, citing each source "
    "by its bracket number like [1], [2]. Be factual and concise."
)

_REWRITE_SYSTEM = (
    "You rewrite a user's follow-up question into a standalone web search "
    "query that will return relevant results from Google-style search.\n"
    "\n"
    "Rules:\n"
    "1. Identify the SUBJECT of the prior research (e.g. the technology or "
    "topic most recently asked about).\n"
    "2. Replace every pronoun or vague reference (it, this, that, those, "
    "the system) in the follow-up with that subject.\n"
    "3. If the follow-up already names its subject, return it unchanged.\n"
    "4. Output ONLY the rewritten query — no commentary, no quotes, no "
    "prefix, max 20 words.\n"
    "\n"
    "Example:\n"
    "Prior research: Previously researched question: What is Redis?\n"
    "Follow-up question: so how does it cache frequent response\n"
    "Rewritten: How does Redis cache frequent responses"
)


# Heuristic for when a rewrite is worth an extra LLM call. On Gemini free
# tier we only get 15 RPM, so we skip the rewrite when the question is
# already self-contained.
_PRONOUN_RE = re.compile(
    r"\b(it|its|this|that|these|those|they|them|their|here|there)\b",
    re.IGNORECASE,
)
_FOLLOWUP_STARTERS = ("so ", "and ", "then ", "also ", "but ")


def _needs_memory_rewrite(question: str) -> bool:
    q = question.strip()
    if not q:
        return False
    if _PRONOUN_RE.search(q):
        return True
    lower = q.lower()
    if any(lower.startswith(s) for s in _FOLLOWUP_STARTERS):
        return True
    if len(q.split()) < 6:  # very short → probably context-dependent
        return True
    return False


async def _rewrite_with_memory(question: str, memory_context: str) -> str:
    """Produce a standalone search query by resolving pronouns against
    prior research. Falls back to the original question on any failure."""
    if not memory_context.strip() or not question.strip():
        return question
    if not _needs_memory_rewrite(question):
        return question
    user = (
        f"Prior research:\n{memory_context}\n\n"
        f"Follow-up question: {question}\n\n"
        "Rewritten standalone search query:"
    )
    try:
        resp = await get_llm().ainvoke(
            [
                SystemMessage(content=_REWRITE_SYSTEM),
                HumanMessage(content=user),
            ]
        )
        rewritten = str(chunk_text(resp.content)).strip().strip('"').strip("'")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Searcher: query rewrite failed, using original: %s", exc)
        return question

    if not rewritten or len(rewritten) > 300:
        return question
    if rewritten.lower() == question.strip().lower():
        return question
    logger.info(
        "Searcher: rewrote query %r -> %r using memory context", question, rewritten
    )
    return rewritten


async def searcher_node(state: ResearchState) -> dict[str, Any]:
    writer = get_stream_writer()
    question = state.get("question", "")
    message_id = f"searcher-{uuid.uuid4()}"

    logger.info("Searcher: starting, question=%r", question)

    writer(
        TextMessageStartEvent(
            type=EventType.TEXT_MESSAGE_START,
            message_id=message_id,
            role="assistant",
        )
    )

    # Pronoun resolution only uses the single most-recent memory (what the
    # user was *just* researching). Passing the full memory_context here
    # would let the rewriter pick the wrong prior subject when multiple
    # topics have been researched.
    recent_memory = state.get("recent_memory", "") or ""
    search_query = await _rewrite_with_memory(question, recent_memory)
    outcome = await tavily_search(search_query)
    sources = outcome["sources"]
    search_error = outcome["error"]
    logger.info(
        "Searcher: tavily returned %d sources (error=%s)",
        len(sources),
        search_error,
    )

    # User-visible fallback banner when web search is unavailable or empty —
    # streamed as real content so the browser panel shows the disclaimer.
    fallback_note = ""
    if search_error:
        fallback_note = (
            f"⚠️ Web search unavailable ({search_error}). "
            "Using model knowledge only.\n\n"
        )
    elif not sources:
        fallback_note = (
            "ℹ️ No web results found for this query. "
            "Using model knowledge only.\n\n"
        )

    collected: list[str] = []
    if fallback_note:
        collected.append(fallback_note)
        writer(
            TextMessageContentEvent(
                type=EventType.TEXT_MESSAGE_CONTENT,
                message_id=message_id,
                delta=fallback_note,
            )
        )

    if sources:
        sources_block = "\n\n".join(
            f"[{i + 1}] {s['title']}\nURL: {s['url']}\nContent: {s['content']}"
            for i, s in enumerate(sources)
        )
    else:
        sources_block = (
            "No web results available. Use your own knowledge and say so."
        )

    user_prompt = f"Query: {question}\n\nSearch results:\n{sources_block}"

    try:
        async for chunk in stream_llm_with_retry(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ],
            agent_name="Searcher",
        ):
            text = chunk_text(chunk.content)
            if not text:
                continue
            collected.append(text)
            writer(
                TextMessageContentEvent(
                    type=EventType.TEXT_MESSAGE_CONTENT,
                    message_id=message_id,
                    delta=text,
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Searcher LLM stream failed: %s", exc)

    full_text = "".join(collected)
    logger.info("Searcher: completed (%d chars)", len(full_text))

    writer(
        TextMessageEndEvent(
            type=EventType.TEXT_MESSAGE_END,
            message_id=message_id,
        )
    )

    await asyncio.sleep(1)  # Gemini free-tier RPM guard

    return {
        "search_results": full_text,
        "sources": sources,
        "resolved_question": search_query,
    }
