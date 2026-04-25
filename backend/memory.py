"""mem0 cloud memory wrapper.

Memory is non-critical — all failures are logged at WARNING and swallowed so
that the research flow continues uninterrupted.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.config import MEM0_API_KEY

logger = logging.getLogger(__name__)

# MemoryClient is imported lazily: the mem0 SDK does env-var discovery at
# import time in some versions, and we want startup to succeed even with
# MEM0_API_KEY unset.
_client: Any | None = None
_client_init_failed = False


def _get_client() -> Any | None:
    global _client, _client_init_failed

    if _client is not None:
        return _client
    if _client_init_failed or not MEM0_API_KEY:
        return None

    try:
        from mem0 import MemoryClient

        _client = MemoryClient(api_key=MEM0_API_KEY)
        logger.info("mem0: client initialized")
        return _client
    except Exception as exc:  # noqa: BLE001
        logger.warning("mem0 client init failed: %s", exc)
        _client_init_failed = True
        return None


_MAX_ANSWER_CHARS = 1500


async def save_research(user_id: str, question: str, answer: str) -> None:
    """Persist a single verbatim memory combining the question and a
    truncated answer. Uses ``infer=False`` so the record is stored
    synchronously and is immediately searchable — mem0's default inferred
    mode is tuned for personal facts and tends to extract nothing from
    research Q&A."""
    client = _get_client()
    if client is None:
        return
    if not question or not answer:
        return

    snippet = answer.strip()
    if len(snippet) > _MAX_ANSWER_CHARS:
        snippet = snippet[:_MAX_ANSWER_CHARS].rstrip() + "…"

    memory_text = (
        f"Previously researched question: {question.strip()}\n"
        f"Key finding: {snippet}"
    )
    messages = [{"role": "user", "content": memory_text}]

    try:
        await asyncio.to_thread(
            client.add, messages, user_id=user_id, infer=False
        )
        logger.info("mem0: saved research for user=%s", user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mem0 save failed for user=%s: %s", user_id, exc)


async def get_context(
    user_id: str,
    question: str,
    semantic_limit: int = 3,
    recent_limit: int = 2,
) -> str:
    """Return relevant memory snippets as a bulleted string.

    Combines semantic search (top-k against the current question) with the
    most recent memories for this user. The recency fallback matters because
    short pronoun-heavy follow-ups like "how does it handle X?" have almost
    no lexical overlap with the stored memory text and mem0's vector search
    drops them below its similarity threshold — but they are exactly the
    cases where conversational context is needed. Empty string when mem0
    is not configured, the user has no memories, or everything errors out.
    """
    client = _get_client()
    if client is None or not question:
        return ""

    semantic_results: list[dict[str, Any]] = []
    try:
        raw = await asyncio.to_thread(
            client.search, query=question, user_id=user_id, limit=semantic_limit
        )
        semantic_results = list(raw or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("mem0 search failed for user=%s: %s", user_id, exc)

    recent_results: list[dict[str, Any]] = []
    try:
        raw_all = await asyncio.to_thread(client.get_all, user_id=user_id)
        entries = list(raw_all or [])
        entries.sort(key=lambda m: m.get("created_at") or "", reverse=True)
        recent_results = entries[:recent_limit]
    except Exception as exc:  # noqa: BLE001
        logger.warning("mem0 get_all failed for user=%s: %s", user_id, exc)

    seen_ids: set[str] = set()
    snippets: list[str] = []
    for entry in semantic_results + recent_results:
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id")
        if eid:
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
        text = (entry.get("memory") or entry.get("text") or "").strip()
        if text:
            snippets.append(text)

    if not snippets:
        return ""

    logger.info(
        "mem0: retrieved %d memories for user=%s (%d semantic + %d recent, after dedupe)",
        len(snippets),
        user_id,
        len(semantic_results),
        len(recent_results),
    )
    return "\n".join(f"- {s}" for s in snippets)


async def get_most_recent(user_id: str) -> str:
    """Return just the single most-recent memory as a string, or "". Used by
    the Searcher for pronoun resolution — we want laser-focus on what the
    user was *just* asking about, not everything semantically adjacent."""
    client = _get_client()
    if client is None:
        return ""
    try:
        raw = await asyncio.to_thread(client.get_all, user_id=user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mem0 get_all (recent) failed for user=%s: %s", user_id, exc)
        return ""

    entries = [m for m in (raw or []) if isinstance(m, dict)]
    if not entries:
        return ""
    entries.sort(key=lambda m: m.get("created_at") or "", reverse=True)
    latest = entries[0]
    text = (latest.get("memory") or latest.get("text") or "").strip()
    return text
