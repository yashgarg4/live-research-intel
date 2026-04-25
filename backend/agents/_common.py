"""Shared helpers for agent nodes: chunk text coercion + retry wrapper."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from google.api_core import exceptions as gax
from langchain_core.messages import BaseMessage

from backend.config import get_llm

logger = logging.getLogger(__name__)

# Transient Gemini failures worth retrying once. Rate limits (429),
# capacity spikes (503), and upstream timeouts (504) are routinely
# recoverable; auth / invalid-arg errors are not.
_RETRYABLE = (
    gax.ResourceExhausted,     # 429
    gax.ServiceUnavailable,    # 503
    gax.DeadlineExceeded,      # 504
    gax.InternalServerError,   # 500
)

DEFAULT_RETRY_DELAY_SEC = 5.0


def chunk_text(content: Any) -> str:
    """Gemini astream chunks can be str or list-of-parts; coerce to str."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
        return "".join(parts)
    return ""


async def stream_llm_with_retry(
    messages: list[BaseMessage],
    *,
    max_retries: int = 1,
    backoff_sec: float = DEFAULT_RETRY_DELAY_SEC,
    agent_name: str = "agent",
) -> AsyncIterator[Any]:
    """Stream LLM tokens, retrying once on transient Gemini failures.

    Retry only occurs if the failure happens *before* any chunk has been
    yielded — once we've emitted partial output, restarting would produce
    torn content, so we propagate instead.
    """
    attempts = max_retries + 1
    for attempt in range(1, attempts + 1):
        yielded = False
        try:
            async for chunk in get_llm().astream(messages):
                yielded = True
                yield chunk
            return
        except _RETRYABLE as exc:
            if yielded or attempt >= attempts:
                logger.error(
                    "%s: LLM stream failed after %d chunk(s) on attempt %d — giving up: %s",
                    agent_name,
                    int(yielded),
                    attempt,
                    exc,
                )
                raise
            logger.warning(
                "%s: transient LLM failure on attempt %d (%s) — retrying in %.1fs",
                agent_name,
                attempt,
                type(exc).__name__,
                backoff_sec,
            )
            await asyncio.sleep(backoff_sec)
