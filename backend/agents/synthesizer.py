"""Synthesizer agent — merges research + critique into a final cited answer
with a confidence score."""
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
from backend.state import ResearchState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a synthesis expert. Combine the research and the critique "
    "into a clear, well-structured answer. Cite your sources inline using "
    "the [n] numbers provided. End your response with exactly this line "
    "on its own: CONFIDENCE: <integer 0-100> where the score reflects "
    "source quality and coverage."
)

_CONFIDENCE_RE = re.compile(r"CONFIDENCE:\s*(\d{1,3})", re.IGNORECASE)


async def synthesizer_node(state: ResearchState) -> dict[str, Any]:
    writer = get_stream_writer()
    question = state.get("question", "")
    search_results = state.get("search_results", "")
    critique = state.get("critique", "")
    sources = state.get("sources", []) or []
    memory_context = state.get("memory_context", "") or ""
    user_refinement = (state.get("user_refinement") or "").strip()
    message_id = f"synthesizer-{uuid.uuid4()}"

    logger.info(
        "Synthesizer: starting (memory_context=%d chars)", len(memory_context)
    )

    writer(
        TextMessageStartEvent(
            type=EventType.TEXT_MESSAGE_START,
            message_id=message_id,
            role="assistant",
        )
    )

    system_prompt = SYSTEM_PROMPT
    if memory_context:
        system_prompt += (
            "\n\nRelevant context from past research with this user:\n"
            f"{memory_context}\n"
            "Prefer consistency with these prior findings when they apply, "
            "and note any contradictions explicitly."
        )

    refinement_line = (
        f"\nUser steering (added mid-run): {user_refinement}\n"
        "Address this refinement explicitly in the final answer.\n"
        if user_refinement
        else ""
    )

    user_prompt = (
        f"Original query: {question}\n\n"
        f"Research findings:\n{search_results}\n\n"
        f"Critique:\n{critique}\n"
        f"{refinement_line}\n"
        "Produce the final synthesized answer now."
    )

    collected: list[str] = []
    try:
        async for chunk in stream_llm_with_retry(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ],
            agent_name="Synthesizer",
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
        logger.exception("Synthesizer LLM stream failed: %s", exc)

    final_text = "".join(collected)
    confidence = _parse_confidence(final_text)
    citations = [
        {"index": i + 1, "title": s.get("title", ""), "url": s.get("url", "")}
        for i, s in enumerate(sources)
    ]

    logger.info(
        "Synthesizer: completed (%d chars), confidence=%d, citations=%d",
        len(final_text),
        confidence,
        len(citations),
    )

    writer(
        TextMessageEndEvent(
            type=EventType.TEXT_MESSAGE_END,
            message_id=message_id,
        )
    )

    await asyncio.sleep(1)

    return {
        "final_answer": final_text,
        "confidence": confidence,
        "citations": citations,
    }


def _parse_confidence(text: str) -> int:
    match = _CONFIDENCE_RE.search(text)
    if not match:
        return 0
    try:
        value = int(match.group(1))
    except ValueError:
        return 0
    return max(0, min(100, value))
