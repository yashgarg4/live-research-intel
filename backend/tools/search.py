"""Web search tools, each mediated by a real MCP server over stdio.

Two thin async wrappers — ``tavily_search`` and ``wikipedia_search`` —
sharing a common ``_call_mcp_tool`` helper. Both return a uniform
``SearchOutcome { sources, error }`` shape so the Searcher can fan out via
``asyncio.gather`` and merge results without per-source branching.

Per-call subprocess spawn (see INTERNAL_NOTES bottleneck #13 for why we
don't hold persistent MCP sessions across FastAPI request tasks).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, TypedDict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

# Resolve the project root once. The MCP server subprocess needs:
#   1. cwd = project root, so ``python -m backend.mcp_servers.X`` resolves
#      the ``backend`` package even when uvicorn was started from somewhere
#      else (the parent's CWD is not necessarily the project root).
#   2. PYTHONPATH = project root, as belt-and-braces in case cwd is ignored
#      by some launcher.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    existing_pp = env.get("PYTHONPATH", "")
    parts = [str(_PROJECT_ROOT)]
    if existing_pp:
        parts.append(existing_pp)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


class SearchOutcome(TypedDict):
    sources: list[dict[str, Any]]
    error: str | None


# ─── Internal helper ────────────────────────────────────────────────────────


async def _call_mcp_tool(
    *,
    server_module: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> SearchOutcome:
    """Spawn ``python -m <server_module>``, run a single tool call, and
    return the parsed ``SearchOutcome``. Any failure (subprocess startup,
    transport error, tool exception) is logged and returned as a populated
    ``error`` string with empty ``sources`` — the Searcher's banner UX
    handles the rest."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", server_module],
        env=_subprocess_env(),
        cwd=str(_PROJECT_ROOT),
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
    except Exception as exc:  # noqa: BLE001 — broad catch is intentional
        logger.warning(
            "MCP call %s/%s failed: %s", server_module, tool_name, exc
        )
        return {
            "sources": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    return _parse_tool_result(result)


def _parse_tool_result(result: Any) -> SearchOutcome:
    """Honor ``structuredContent`` first, fall back to JSON-decoding
    ``TextContent`` items."""
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

    logger.warning("MCP tool returned unparseable result: %r", result)
    return {"sources": [], "error": "MCP returned no parseable payload"}


def _coerce_outcome(data: dict[str, Any]) -> SearchOutcome:
    sources = data.get("sources") or []
    if not isinstance(sources, list):
        sources = []
    error = data.get("error")
    if error is not None and not isinstance(error, str):
        error = str(error)
    return {"sources": sources, "error": error}


# ─── Public API ─────────────────────────────────────────────────────────────


async def tavily_search(query: str, max_results: int = 5) -> SearchOutcome:
    """Tavily web search via MCP."""
    return await _call_mcp_tool(
        server_module="backend.mcp_servers.tavily_server",
        tool_name="tavily_search",
        arguments={"query": query, "max_results": max_results},
    )


async def wikipedia_search(query: str, max_results: int = 3) -> SearchOutcome:
    """Wikipedia (MediaWiki API) search via MCP."""
    return await _call_mcp_tool(
        server_module="backend.mcp_servers.wikipedia_server",
        tool_name="wikipedia_search",
        arguments={"query": query, "max_results": max_results},
    )
