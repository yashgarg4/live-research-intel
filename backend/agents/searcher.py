"""Searcher agent — fan-outs Tavily + Wikipedia (both via real MCP servers)
in parallel, merges results with continuous indexing, then streams a Gemini
summary."""
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
from backend.tools.search import tavily_search, wikipedia_search

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


def _build_fallback_note(
    tavily_outcome: dict[str, Any],
    wiki_outcome: dict[str, Any],
) -> str:
    """Banner copy reflecting which MCP sources succeeded / failed / were
    empty. Returned text is streamed verbatim into the Searcher panel."""
    tavily_sources = tavily_outcome.get("sources") or []
    wiki_sources = wiki_outcome.get("sources") or []
    tavily_err = tavily_outcome.get("error")
    wiki_err = wiki_outcome.get("error")
    total = len(tavily_sources) + len(wiki_sources)

    if total == 0:
        if tavily_err and wiki_err:
            return (
                f"⚠️ All sources unavailable. "
                f"Web: {tavily_err}. Wikipedia: {wiki_err}. "
                "Using model knowledge only.\n\n"
            )
        if tavily_err:
            return (
                f"⚠️ Web search unavailable ({tavily_err}) "
                "and Wikipedia returned nothing. Using model knowledge only.\n\n"
            )
        if wiki_err:
            return (
                f"⚠️ Wikipedia unavailable ({wiki_err}) "
                "and web search returned nothing. Using model knowledge only.\n\n"
            )
        return (
            "ℹ️ No results found across web or Wikipedia. "
            "Using model knowledge only.\n\n"
        )

    notes: list[str] = []
    if tavily_err:
        notes.append(f"Web search failed ({tavily_err})")
    elif not tavily_sources:
        notes.append("Web search returned no results")
    if wiki_err:
        notes.append(f"Wikipedia failed ({wiki_err})")
    elif not wiki_sources:
        notes.append("Wikipedia returned no results")

    if notes:
        return f"⚠️ Partial sources only — {'; '.join(notes)}.\n\n"
    return ""


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

    # Fan out across two MCP servers in parallel — both subprocess spawns
    # happen concurrently via asyncio.gather, so total wall time is bounded
    # by the slower of the two rather than the sum.
    tavily_outcome, wiki_outcome = await asyncio.gather(
        tavily_search(search_query, max_results=5),
        wikipedia_search(search_query, max_results=3),
    )

    # Tag and merge with continuous [1]…[N] indexing for the Synthesizer.
    sources: list[dict[str, Any]] = []
    for s in tavily_outcome["sources"]:
        sources.append({**s, "source_type": "web"})
    for s in wiki_outcome["sources"]:
        sources.append({**s, "source_type": "wikipedia"})

    logger.info(
        "Searcher: tavily=%d wiki=%d (tavily_err=%s, wiki_err=%s)",
        len(tavily_outcome["sources"]),
        len(wiki_outcome["sources"]),
        tavily_outcome["error"],
        wiki_outcome["error"],
    )

    # User-visible banner — surface partial-failure as well as total-failure.
    fallback_note = _build_fallback_note(tavily_outcome, wiki_outcome)

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
            f"[{i + 1}] ({s.get('source_type','web')}) {s['title']}\n"
            f"URL: {s['url']}\nContent: {s['content']}"
            for i, s in enumerate(sources)
        )
    else:
        sources_block = (
            "No web or Wikipedia results available. "
            "Use your own knowledge and say so."
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
