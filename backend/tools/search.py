"""Tavily search, mediated by a real MCP server over stdio transport.

The ``tavily_search`` function is the public API and keeps the same
``SearchOutcome`` shape so the Searcher node doesn't change. Internally
each call spawns the MCP server (``backend.mcp_servers.tavily_server``) as
a short-lived subprocess, opens a stdio MCP session, calls the
``tavily_search`` tool, and tears the connection down.

Why per-call rather than persistent? The MCP Python SDK's ``stdio_client``
uses an anyio task group internally that's affinity-bound to the task that
opened it. Holding the session across multiple FastAPI request tasks
triggers ``"Attempted to exit cancel scope in a different task than it was
entered in"`` at teardown. Per-call avoids the issue entirely; the startup
overhead (~200–400 ms) is dwarfed by the subsequent LLM streaming.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any, TypedDict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class SearchOutcome(TypedDict):
    sources: list[dict[str, Any]]
    error: str | None


_TOOL_NAME = "tavily_search"


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "backend.mcp_servers.tavily_server"],
        env=None,  # inherit (TAVILY_API_KEY etc.)
    )


async def tavily_search(query: str, max_results: int = 5) -> SearchOutcome:
    """Public API — same shape as the in-process version, now mediated by
    a real MCP server. Every failure is logged and returned as a
    SearchOutcome with ``error`` set, so the Searcher's fallback banner
    fires without the graph crashing."""
    try:
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    _TOOL_NAME,
                    {"query": query, "max_results": max_results},
                )
    except Exception as exc:  # noqa: BLE001 — broad catch is intentional
        logger.warning("MCP tavily_search call failed: %s", exc)
        return {
            "sources": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    return _parse_tool_result(result)


def _parse_tool_result(result: Any) -> SearchOutcome:
    """FastMCP returns a ``CallToolResult``. For dict-returning tools the
    payload is in ``content`` as a list of ``TextContent`` items with JSON
    in ``.text``. We honor ``structuredContent`` first when the SDK exposes
    it, then fall back to parsing the text contents."""
    structured = getattr(result, "structuredContent", None) or getattr(
        result, "structured_content", None
    )
    if isinstance(structured, dict):
        return _coerce_outcome(structured)

    content = getattr(result, "content", None) or []
    for item in content:
        text = getattr(item, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return _coerce_outcome(parsed)

    logger.warning("MCP tavily_search returned unparseable result: %r", result)
    return {"sources": [], "error": "MCP returned no parseable payload"}


def _coerce_outcome(data: dict[str, Any]) -> SearchOutcome:
    sources = data.get("sources") or []
    if not isinstance(sources, list):
        sources = []
    error = data.get("error")
    if error is not None and not isinstance(error, str):
        error = str(error)
    return {"sources": sources, "error": error}
