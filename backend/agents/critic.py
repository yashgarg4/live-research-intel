"""Critic agent — reviews Searcher's output, raises one follow-up."""
from __future__ import annotations

import asyncio
import logging
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
    "You are a critical analyst. Review the research findings below. "
    "Identify any gaps, biases, or missing perspectives. Raise exactly one "
    "sharp follow-up question the research did not answer."
)


async def critic_node(state: ResearchState) -> dict[str, Any]:
    writer = get_stream_writer()
    question = state.get("question", "")
    search_results = state.get("search_results", "")
    user_refinement = (state.get("user_refinement") or "").strip()
    message_id = f"critic-{uuid.uuid4()}"

    logger.info(
        "Critic: starting (user_refinement=%d chars)", len(user_refinement)
    )

    writer(
        TextMessageStartEvent(
            type=EventType.TEXT_MESSAGE_START,
            message_id=message_id,
            role="assistant",
        )
    )

    refinement_line = (
        f"\nUser steering (added mid-run): {user_refinement}\n"
        "Factor this refinement explicitly into your critique.\n"
        if user_refinement
        else ""
    )

    user_prompt = (
        f"Original query: {question}\n\n"
        f"Research findings:\n{search_results}\n"
        f"{refinement_line}\n"
        "Produce your critique and end with one follow-up question."
    )

    collected: list[str] = []
    try:
        async for chunk in stream_llm_with_retry(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ],
            agent_name="Critic",
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
        logger.exception("Critic LLM stream failed: %s", exc)

    critique = "".join(collected)
    logger.info("Critic: completed (%d chars)", len(critique))

    writer(
        TextMessageEndEvent(
            type=EventType.TEXT_MESSAGE_END,
            message_id=message_id,
        )
    )

    await asyncio.sleep(1)

    return {"critique": critique}
