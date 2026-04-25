"""Tavily search tool wrapper — async, returns a tagged outcome so the
caller can distinguish three cases: success-with-results, success-with-no-
results, and a failure (missing key, network, SSL, rate limit, etc.)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, TypedDict

from tavily import TavilyClient

from backend.config import TAVILY_API_KEY

logger = logging.getLogger(__name__)

_client: TavilyClient | None = None


class SearchOutcome(TypedDict):
    sources: list[dict[str, Any]]
    error: str | None  # None = call succeeded; str describes the failure.


def _get_client() -> TavilyClient | None:
    global _client
    if not TAVILY_API_KEY:
        return None
    if _client is None:
        _client = TavilyClient(api_key=TAVILY_API_KEY)
    return _client


async def tavily_search(query: str, max_results: int = 5) -> SearchOutcome:
    client = _get_client()
    if client is None:
        return {"sources": [], "error": "TAVILY_API_KEY is not configured"}

    try:
        raw = await asyncio.to_thread(
            client.search,
            query=query,
            max_results=max_results,
            search_depth="basic",
        )
    except Exception as exc:  # noqa: BLE001 — tavily raises several types
        logger.warning("Tavily search failed: %s", exc)
        return {
            "sources": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    sources = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
        }
        for r in raw.get("results", [])
    ]
    return {"sources": sources, "error": None}
