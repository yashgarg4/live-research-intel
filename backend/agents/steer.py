"""Human-in-the-loop steering nodes that run between Searcher and Critic.

Why two nodes? LangGraph re-runs a node from the top when the graph is
resumed after an ``interrupt()``. Putting the ``writer(...)`` call and the
``interrupt()`` call in the same node would emit the "awaiting_input"
custom event twice — once on the initial run and once on resume. Splitting
them means the emit is idempotent (the prompt node is never re-entered on
resume) and only the interrupt node re-runs, where ``interrupt()`` now
returns the resume value instead of raising.
"""
from __future__ import annotations

import logging
from typing import Any

from ag_ui.core import CustomEvent, EventType
from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from backend.state import ResearchState

logger = logging.getLogger(__name__)


async def ask_for_refinement_node(state: ResearchState) -> dict[str, Any]:
    """Emit an AG-UI CustomEvent telling the UI to show a refinement input.
    No state change — this node purely signals."""
    writer = get_stream_writer()
    question = state.get("question", "")
    search_preview = (state.get("search_results") or "").strip()
    if len(search_preview) > 400:
        search_preview = search_preview[:400].rstrip() + "…"

    logger.info("HITL: emitting awaiting_input custom event")
    writer(
        CustomEvent(
            type=EventType.CUSTOM,
            name="awaiting_input",
            value={
                "prompt": (
                    "Want to refine the query before the Critic runs? "
                    "Leave blank or type 'skip' to continue as-is."
                ),
                "question": question,
                "search_preview": search_preview,
            },
        )
    )
    return {}


async def await_refinement_node(state: ResearchState) -> dict[str, Any]:
    """Pause the graph and wait for user input. On resume, the value passed
    via ``Command(resume=...)`` becomes the return of ``interrupt()``."""
    refinement = interrupt({"phase": "refinement"})

    if isinstance(refinement, str):
        cleaned = refinement.strip()
        if cleaned and cleaned.lower() != "skip":
            logger.info("HITL: user refinement=%r", cleaned)
            return {"user_refinement": cleaned}

    logger.info("HITL: user skipped refinement")
    return {"user_refinement": ""}
