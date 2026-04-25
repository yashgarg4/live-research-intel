# Live Research Intelligence

[![CI](https://github.com/yashgarg4/live-research-intel/actions/workflows/ci.yml/badge.svg)](https://github.com/yashgarg4/live-research-intel/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](#license)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![Node 20+](https://img.shields.io/badge/Node-20%2B-339933?logo=node.js&logoColor=white)

https://github.com/user-attachments/assets/60460ef7-d1cf-4c90-80ca-4c465daddd57

A live multi-agent research system. Ask any question and three specialist LangGraph agents — **Searcher**, **Critic**, **Synthesizer** — run in a coordinated graph while every reasoning token streams to the browser in real time over the AG-UI protocol. You watch each agent think as it happens, optionally steer the run mid-flight, and end up with a cited answer plus a confidence score.

The full 2026 agentic stack, end-to-end:

- **AG-UI** for typed agent ↔ UI event streaming (no polling, no spinners).
- **LangGraph** for multi-agent orchestration with a shared `TypedDict` state.
- **Two real MCP servers** (stdio transport, JSON-RPC) — one for Tavily web search, one for Wikipedia. The Searcher fans out across both in parallel via `asyncio.gather` and merges results with continuous citation indexing.
- **Live tool-call telemetry** — every MCP call surfaces `tool_call_start` / `tool_call_end` AG-UI custom events to the browser, rendered as live pill cards inside the Searcher panel (running / done / failed with source counts and timing).
- **mem0** for cross-session memory so follow-ups build on prior research.
- **Human-in-the-loop steering** — the graph pauses between agents and the UI gets the steering wheel.

---

## Demo (60 seconds)

1. Type any question — e.g. *"What is Redis?"*
2. The four-node **graph topology** band lights up node-by-node as the graph executes — each pill goes from idle slate to its accent-coloured pulse, then to an emerald check.
3. Three colour-coded panels (teal / amber / rose) fill token-by-token: the Searcher summarises 5 Tavily web sources + 3 Wikipedia extracts, the Critic raises gaps and a follow-up question, the Synthesizer composes the final answer.
4. Between Searcher and Critic the graph **pauses** (the *Steer* node lights up indigo) and an indigo card appears: *"Graph paused — your turn"*. Type a refinement (e.g. *"focus on enterprise use cases"*) or hit *Skip*.
5. The run resumes. The Critic and Synthesizer factor in your steering. The final result card shows the answer with rendered markdown, clickable inline `[N]` citations that jump to the source list, a *"Steered with"* chip showing your refinement, and a colour-banded confidence badge.
6. Ask a follow-up like *"so how does it cache frequent response"*. The Searcher's query rewriter resolves "it" to "Redis" using your prior memory. The Synthesizer opens with *"Based on your prior research…"*.

---

## Why this stack is state-of-the-art in 2026

| Older norm                                                              | This project                                                                                                              |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Wait-then-render. Backend returns one big JSON, UI shows a spinner.     | **AG-UI SSE** streams every token as it's produced. UI renders reasoning in flight.                                       |
| Bespoke REST schemas, no interop between agent frameworks.              | **AG-UI is an open protocol** with typed events (`TextMessageContent`, `CustomEvent`, `RunStarted`, `RunFinished`).       |
| Hand-rolled `while not done: call_llm()` loops.                         | **LangGraph `StateGraph`** with explicit nodes, typed shared state, native streaming, and `interrupt()` for HITL.          |
| Memory = stuff the chat log into the next prompt.                       | **mem0 vector memory** — per-user, semantic + recency merge, injected into the Synthesizer's system prompt.                |
| Tools are ad-hoc Python functions glued in by hand.                     | **Two real MCP servers** (Tavily + Wikipedia) over stdio JSON-RPC; Searcher fans out in parallel and surfaces live tool-call cards in the UI. |
| CopilotKit-locked frontends needing a Node.js runtime middleware proxy. | **AG-UI-native frontend** — a 60-line `useResearchStream` hook with `fetch` + `ReadableStream`. Zero middleware.            |
| `certifi` bundle breaks behind corporate SSL inspection.                | **`truststore.inject_into_ssl()`** uses the OS trust store. Corporate CA chains work without code changes.                 |

---

## Architecture

```
┌──────────────────────┐    fetch POST + SSE     ┌─────────────────────────────────────────────────────────────┐
│   React SPA (Vite)   │  ─────────────────────▶ │   FastAPI                                                    │
│                      │  ◀── AG-UI SSE ────     │     POST /research                                           │
│  ┌────────────────┐  │     text/event-stream   │     POST /research/resume                                    │
│  │ SearchBar      │  │                         │                                                              │
│  └────────────────┘  │                         │   ┌──────────────────────────────────────────────────────┐  │
│  ┌────┬────┬─────┐   │                         │   │  LangGraph StateGraph[ResearchState]                  │  │
│  │ S  │ C  │ Syn │   │  per-agent live stream  │   │                                                      │  │
│  └────┴────┴─────┘   │                         │   │   Searcher → ask_for_refinement →                    │  │
│  ▲ tool-call strip   │  CustomEvent: tool_call_*│   │   await_refinement (interrupt) →                     │  │
│  ┌────────────────┐  │  CustomEvent: awaiting_input │ Critic → Synthesizer                                 │  │
│  │ RefineInput    │  │  CustomEvent: citations │   │                                                      │  │
│  └────────────────┘  │  CustomEvent: confidence│   └──────────────────────────────────────────────────────┘  │
│  ┌────────────────┐  │                         │        │            │            │                          │
│  │ ResultCard     │  │                         │        ▼            ▼            ▼                          │
│  └────────────────┘  │                         │   ┌────────┐    ┌─────────┐   ┌─────┐                       │
└──────────────────────┘                         │   │ Gemini │    │  mem0   │   │ MCP │  fan-out             │
        │                                        │   │ stream │    │  cloud  │   │     │  asyncio.gather      │
        │  X-User-Id (localStorage)              │   └────────┘    └─────────┘   └─────┘                       │
        ▼                                        │                                  │                           │
   Persistent per-browser ID                     │                ┌─────────────────┴───────────────────┐       │
                                                 │                ▼                                     ▼       │
                                                 │   ┌──────────────────────┐     ┌──────────────────────────┐ │
                                                 │   │  tavily_server.py    │     │  wikipedia_server.py     │ │
                                                 │   │  (FastMCP, stdio)    │     │  (FastMCP, stdio)        │ │
                                                 │   │  → Tavily web search │     │  → MediaWiki action API  │ │
                                                 │   └──────────────────────┘     └──────────────────────────┘ │
                                                 │  truststore.inject_into_ssl()  (OS cert store)              │
                                                 └─────────────────────────────────────────────────────────────┘
```

### Layer breakdown

- **Frontend** — Vite + React 19 + TypeScript + Tailwind v4. The `useResearchStream` hook fetches the SSE stream, parses events, and routes each `TextMessage*` event into a per-agent state slice keyed by `messageId` prefix (`searcher-…`, `critic-…`, `synthesizer-…`). `CustomEvent`s carry citations, confidence, the awaiting-input prompt, and live tool-call telemetry. Markdown rendering via `react-markdown` + `remark-gfm` with `@tailwindcss/typography` styling.
- **Backend** — FastAPI + LangGraph + langchain-google-genai + mem0ai + the `mcp` Python SDK (client side). Each agent node pushes AG-UI events through `langgraph.config.get_stream_writer()`; `main.py` consumes `graph.astream(stream_mode=["custom","values","updates"])` and forwards events as SSE while watching the `updates` channel for `__interrupt__`.
- **MCP fan-out** — The Searcher wraps each tool invocation in `_instrumented_tool_call()`, which emits `tool_call_start` before and `tool_call_end` after (with `source_count`, `error`, `duration_ms`). The two MCP server subprocesses are spawned concurrently via `asyncio.gather`, results are merged with continuous `[1]…[N]` indexing and a `source_type` field tagging each entry as `web` or `wikipedia`. Subprocess `cwd` and `PYTHONPATH` are set explicitly so the `backend.mcp_servers.*` module paths resolve regardless of where uvicorn was launched from.
- **HITL pause** — `langgraph.types.interrupt()` is called from `await_refinement_node` between Searcher and Critic. State is checkpointed via `InMemorySaver`. The browser receives a `CustomEvent(name="awaiting_input")`, the SSE closes (no `RUN_FINISHED`), and a follow-up `POST /research/resume` carries the user's refinement back via `Command(resume=...)`.

---

## Features

- **Live graph topology** — a four-node visualisation of the LangGraph (Searcher → Steer → Critic → Synthesizer) sits above the agent panels. Each node lights up with its accent colour while it's running, flips to an emerald check when done. Computed purely from the live AG-UI event stream — no extra protocol surface.
- **Live token streaming** for every agent. No buffering, no spinners.
- **Two-source fan-out** — Tavily web search and Wikipedia run in parallel via real MCP servers; results are merged into a single citation list and the LLM picks the best mix per question.
- **Live tool-call cards** — every MCP invocation surfaces in the Searcher panel as a pill that transitions running → done with `5 sources · 1.4s` summaries (or red on failure). The MCP boundary is *visible* to the user, not just in logs.
- **Memory-aware follow-ups.** Pronouns like *"how does it work"* are resolved against your most-recent research before the Searcher hits Tavily/Wikipedia, so external-search results stay on-topic.
- **Human-in-the-loop steering.** The graph pauses between agents; you can refine, skip, or accept-as-is. The refinement is woven into the Critic and Synthesizer prompts.
- **Citations as first-class data.** The synthesizer cites inline (`[1, 3]`); the UI rewrites those markers into anchor links that jump to the source list. Each source is a real Tavily / Wikipedia URL, never hallucinated.
- **Confidence scoring.** The Synthesizer ends every answer with a `CONFIDENCE: N` line that's parsed and rendered as a colour-banded badge.
- **Graceful partial-failure UX.** When one source fails (e.g. Tavily quota) and the other succeeds, the Searcher streams a *"Partial sources only — Web search failed (…)"* banner and proceeds with what it has. Both fail → falls back to model knowledge with a clear disclaimer.
- **Transient retries.** Gemini 429 / 500 / 503 / 504 errors are automatically retried once after 5 s — only when no chunks have yet been yielded, so partial output is never re-emitted.
- **Per-user persistent memory.** Browser keeps a `localStorage` UUID and sends it as `X-User-Id` on every request; mem0 keys memories by that.
- **Markdown rendering** in every panel and the final result with `@tailwindcss/typography`, including code blocks, lists, headings, bold/italic, and inline citations.
- **Works behind corporate proxies** — `truststore` is injected at startup so OS cert stores (Windows, macOS, Linux) handle the TLS chain.

---

## Quick start

Requires **Python 3.11+** and **Node 20+**.

```bash
# 1. Clone and enter
git clone <this-repo>
cd live_research_intel

# 2. Add your API keys
cp .env.example .env
#   GOOGLE_API_KEY  — https://aistudio.google.com/app/apikey  (free tier: 20 req/day on flash-lite)
#   TAVILY_API_KEY  — https://tavily.com                       (free tier: 1000 searches/mo)
#   MEM0_API_KEY    — https://mem0.ai                          (optional — memory degrades to no-op)

# 3. Python venv + deps
python -m venv venv
source venv/bin/activate          # Linux / macOS
venv\Scripts\activate             # Windows PowerShell / cmd
pip install -r requirements.txt

# 4. Frontend deps
cd frontend && npm install && cd ..

# 5. Run both
make dev
```

The UI lives at <http://127.0.0.1:5173>; the backend at <http://127.0.0.1:8000>. FastAPI's interactive docs are at `/docs`.

If GNU `make` isn't installed (Windows), use two terminals:

```bash
# Terminal 1 — venv activated
uvicorn backend.main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

---

## API

| Method | Path                  | Notes                                                                                          |
| ------ | --------------------- | ---------------------------------------------------------------------------------------------- |
| GET    | `/health`             | `{"status":"ok"}`                                                                              |
| POST   | `/research`           | Start a run. Body is `RunAgentInput`-compatible. Headers: `X-User-Id` (defaults to `anonymous`). |
| POST   | `/research/resume`    | Resume a paused run. Body: `{"thread_id": "<id>", "user_input": "<refinement or 'skip'>"}`.     |
| GET    | `/docs`               | FastAPI Swagger UI.                                                                            |

Both research endpoints return `text/event-stream`. Event types you'll see:

- `RUN_STARTED` / `RUN_FINISHED` — run boundaries.
- `TEXT_MESSAGE_START` / `TEXT_MESSAGE_CONTENT` / `TEXT_MESSAGE_END` — per-agent token streams. `messageId` prefix encodes the agent.
- `CUSTOM` with `name = "tool_call_start"` — `{tool_call_id, tool_name, args, parent_message_id}` emitted before each MCP invocation.
- `CUSTOM` with `name = "tool_call_end"` — `{tool_call_id, tool_name, source_count, error, duration_ms}` emitted when the call returns.
- `CUSTOM` with `name = "awaiting_input"` — graph paused; payload carries `{prompt, question, search_preview}`.
- `CUSTOM` with `name = "citations"` — array of `{index, title, url}`.
- `CUSTOM` with `name = "confidence"` — integer 0–100.

If `/research` finishes its first segment and you see `awaiting_input` followed by an SSE close (no `RUN_FINISHED`), the run is paused in the checkpointer. Call `/research/resume` with the same `thread_id` to continue.

---

## Project layout

```
live_research_intel/
├── backend/
│   ├── main.py                 FastAPI app + /research + /research/resume
│   ├── graph.py                LangGraph StateGraph wiring (with InMemorySaver)
│   ├── state.py                ResearchState TypedDict
│   ├── config.py               env vars + truststore + lazy Gemini factory
│   ├── memory.py               mem0 save_research / get_context / get_most_recent
│   ├── agents/
│   │   ├── _common.py          chunk_text + stream_llm_with_retry
│   │   ├── searcher.py         query rewrite + parallel MCP fan-out + tool-call telemetry + Gemini summary
│   │   ├── steer.py            HITL ask_for_refinement + await_refinement nodes
│   │   ├── critic.py           gap analysis + one follow-up question
│   │   └── synthesizer.py      final answer + CONFIDENCE + citations
│   ├── mcp_servers/
│   │   ├── tavily_server.py    FastMCP server — Tavily web search over stdio
│   │   └── wikipedia_server.py FastMCP server — MediaWiki action API over stdio
│   └── tools/search.py         MCP client — fans out to both servers, _instrumented_tool_call()
├── frontend/
│   ├── src/
│   │   ├── App.tsx             SearchBar + GraphViz + 3 panels + RefineInput + ResultCard
│   │   ├── types.ts            AG-UI event union + StreamState + Citation + ToolCall
│   │   ├── hooks/useResearchStream.ts   fetch SSE parser, run() + resume()
│   │   └── components/         SearchBar / GraphViz / AgentPanel / ToolCallStrip / RefineInput / ResultCard
│   ├── vite.config.ts          Tailwind v4 plugin, port 5173
│   └── package.json
├── requirements.txt
├── Makefile                    install / backend / frontend / dev / clean
├── .env.example
└── README.md                   you are here
```

---

## Corporate networks

TLS calls to Google / Tavily / mem0 use the OS trust store via [`truststore`](https://pypi.org/project/truststore/), injected at startup in `backend/config.py`. This is what lets the project work behind SSL-inspection proxies that rewrite certificates — otherwise `certifi` rejects the corporate root CA and all three providers fail with `CERTIFICATE_VERIFY_FAILED`.

---

## Coding notes

- All async — FastAPI, LangGraph nodes, Gemini `astream`, Tavily via `asyncio.to_thread`.
- 1 s sleep between nodes to respect Gemini free-tier RPM.
- CORS explicitly allows `Content-Type` and `X-User-Id` (required since `allow_credentials=True` bans wildcard headers).
