"""Wikipedia search exposed as a real MCP server (stdio transport).

Run as a subprocess from the backend:

    python -m backend.mcp_servers.wikipedia_server

Exposes a single tool, ``wikipedia_search(query, max_results)``. Uses the
public MediaWiki ``action=query&generator=search`` endpoint to fetch top-K
matching pages with their lead-section extracts in one round trip — no API
key needed.

Returns the same ``{"sources": [...], "error": ...}`` shape as the Tavily
MCP server, so the Searcher can merge the two outcomes uniformly.

Logging goes to stderr because stdout is reserved for MCP JSON-RPC.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

# Ensure the project root is importable when launched as a subprocess.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# OS trust store for corporate SSL inspection (same as the main backend).
try:  # pragma: no cover — best-effort
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass

import httpx  # noqa: E402 — must come after sys.path/truststore tweaks
from mcp.server.fastmcp import FastMCP  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s | %(levelname)s | mcp.wikipedia | %(message)s",
)
logger = logging.getLogger("mcp.wikipedia")

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "live-research-intel/0.1 (https://example.invalid; mcp.wikipedia)"
EXTRACT_CHARS = 1500

mcp = FastMCP("wikipedia-search")


@mcp.tool()
def wikipedia_search(query: str, max_results: int = 3) -> dict[str, Any]:
    """Search Wikipedia and return top-K page lead extracts.

    Returns ``{"sources": [{title, url, content}, ...], "error": str | None}``.
    ``error`` is None on success even with zero results; a non-None string
    describes the failure (HTTP, parsing, network, etc.).
    """
    if not query or not query.strip():
        return {"sources": [], "error": "empty query"}

    try:
        with httpx.Client(
            timeout=10.0,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = client.get(
                WIKIPEDIA_API_URL,
                params={
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": query,
                    "gsrlimit": str(max_results),
                    "prop": "extracts",
                    "exintro": "1",
                    "explaintext": "1",
                    "redirects": "1",
                    "format": "json",
                    "formatversion": "2",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Wikipedia search failed: %s", exc)
        return {"sources": [], "error": f"{type(exc).__name__}: {exc}"}

    pages = (data.get("query") or {}).get("pages") or []
    # formatversion=2 returns a list; older returns a dict — handle both.
    if isinstance(pages, dict):
        pages = list(pages.values())

    pages_sorted = sorted(pages, key=lambda p: p.get("index", 999))

    sources: list[dict[str, Any]] = []
    for page in pages_sorted:
        title = (page.get("title") or "").strip()
        extract = (page.get("extract") or "").strip()
        if not title or not extract:
            continue
        url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
        if len(extract) > EXTRACT_CHARS:
            extract = extract[:EXTRACT_CHARS].rstrip() + "…"
        sources.append({"title": title, "url": url, "content": extract})

    logger.info(
        "wikipedia_search query=%r returned %d sources", query, len(sources)
    )
    return {"sources": sources, "error": None}


if __name__ == "__main__":
    mcp.run()
