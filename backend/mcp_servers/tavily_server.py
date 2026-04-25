"""Tavily search exposed as a real MCP server (stdio transport).

Run as a subprocess from the backend:

    python -m backend.mcp_servers.tavily_server

Exposes a single tool, ``tavily_search(query, max_results)``, that returns a
JSON-encoded ``{"sources": [...], "error": ...}`` payload. The shape matches
the in-process ``SearchOutcome`` we used to return directly, so the Searcher
keeps the same downstream code.

Logging goes to stderr because the JSON-RPC framing on stdout must stay
clean for the MCP transport.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

# Ensure the project root is importable when this server is launched as a
# subprocess (-m makes it work too, but spawning via path argument also
# needs to find ``backend.config``).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Use the OS trust store before anything else hits the network — corporate
# SSL inspection re-signs Tavily traffic with an internal CA that certifi
# doesn't know about.
try:  # pragma: no cover — best-effort
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass

from dotenv import load_dotenv  # noqa: E402  — must come after sys.path tweak
from mcp.server.fastmcp import FastMCP  # noqa: E402
from tavily import TavilyClient  # noqa: E402

load_dotenv(_PROJECT_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s | %(levelname)s | mcp.tavily | %(message)s",
)
logger = logging.getLogger("mcp.tavily")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

mcp = FastMCP("tavily-search")
_client: TavilyClient | None = None


def _get_client() -> TavilyClient | None:
    global _client
    if not TAVILY_API_KEY:
        return None
    if _client is None:
        _client = TavilyClient(api_key=TAVILY_API_KEY)
    return _client


@mcp.tool()
def tavily_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Run a Tavily web search.

    Returns a JSON-friendly ``{"sources": [...], "error": str | None}``
    payload. ``error`` is ``None`` on success (even with zero results); a
    non-None string describes the failure (missing key, SSL, rate limit,
    network, etc.).
    """
    client = _get_client()
    if client is None:
        logger.warning("TAVILY_API_KEY missing — returning empty outcome")
        return {"sources": [], "error": "TAVILY_API_KEY is not configured"}

    try:
        raw = client.search(
            query=query,
            max_results=max_results,
            search_depth="basic",
        )
    except Exception as exc:  # noqa: BLE001 — Tavily raises a few types
        logger.warning("Tavily search failed: %s", exc)
        return {"sources": [], "error": f"{type(exc).__name__}: {exc}"}

    sources = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
        }
        for r in raw.get("results", [])
    ]
    logger.info("tavily_search query=%r returned %d sources", query, len(sources))
    return {"sources": sources, "error": None}


if __name__ == "__main__":
    # Default transport is stdio.
    mcp.run()
