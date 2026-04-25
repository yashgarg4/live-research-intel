# Live Research Intelligence

A live multi-agent research system. Ask any question and three specialist LangGraph agents — **Searcher**, **Critic**, **Synthesizer** — run in a coordinated graph while every reasoning token streams to the browser in real time over the AG-UI protocol. You watch each agent think as it happens, optionally steer the run mid-flight, and end up with a cited answer plus a confidence score.

The full 2026 agentic stack, end-to-end:

- **AG-UI** for typed agent ↔ UI event streaming (no polling, no spinners).
- **LangGraph** for multi-agent orchestration with a shared `TypedDict` state.
- **Real MCP server** (stdio transport, JSON-RPC) hosting Tavily web search — the Searcher consumes it via the `mcp` Python client.
- **mem0** for cross-session memory so follow-ups build on prior research.
- **Human-in-the-loop steering** — the graph pauses between agents and the UI gets the steering wheel.

---

## Demo (60 seconds)

1. Type any question — e.g. *"What is Redis?"*
2. Three colour-coded panels (teal / amber / rose) fill token-by-token: the Searcher summarises 5 Tavily web sources, the Critic raises gaps and a follow-up question, the Synthesizer composes the final answer.
3. Between Searcher and Critic the graph **pauses** and an indigo card appears: *"Graph paused — your turn"*. Type a refinement (e.g. *"focus on enterprise use cases"*) or hit *Skip*.
4. The run resumes. The Critic and Synthesizer factor in your steering. The final result card shows the answer with rendered markdown, clickable inline `[N]` citations that jump to the source list, a *"Steered with"* chip showing your refinement, and a colour-banded confidence badge.
5. Ask a follow-up like *"so how does it cache frequent response"*. The Searcher's query rewriter resolves "it" to "Redis" using your prior memory. The Synthesizer opens with *"Based on your prior research…"*.

---

## Why this stack is state-of-the-art in 2026

| Older norm                                                              | This project                                                                                                              |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Wait-then-render. Backend returns one big JSON, UI shows a spinner.     | **AG-UI SSE** streams every token as it's produced. UI renders reasoning in flight.                                       |
| Bespoke REST schemas, no interop between agent frameworks.              | **AG-UI is an open protocol** with typed events (`TextMessageContent`, `CustomEvent`, `RunStarted`, `RunFinished`).       |
| Hand-rolled `while not done: call_llm()` loops.                         | **LangGraph `StateGraph`** with explicit nodes, typed shared state, native streaming, and `interrupt()` for HITL.          |
| Memory = stuff the chat log into the next prompt.                       | **mem0 vector memory** — per-user, semantic + recency merge, injected into the Synthesizer's system prompt.                |
| Tools are ad-hoc Python functions glued in by hand.                     | **Real MCP server** for Tavily — stdio JSON-RPC, `mcp.server.fastmcp` on the server, `mcp.client.stdio` on the agent.       |
| CopilotKit-locked frontends needing a Node.js runtime middleware proxy. | **AG-UI-native frontend** — a 60-line `useResearchStream` hook with `fetch` + `ReadableStream`. Zero middleware.            |
| `certifi` bundle breaks behind corporate SSL inspection.                | **`truststore.inject_into_ssl()`** uses the OS trust store. Corporate CA chains work without code changes.                 |

---

## Architecture

```
┌──────────────────────┐       fetch POST + SSE       ┌───────────────────────────────────────────────────┐
│   React SPA (Vite)   │  ─────────────────────────▶  │   FastAPI                                          │
│                      │  ◀── AG-UI SSE events ────   │     POST /research                                 │
│  ┌────────────────┐  │     text/event-stream        │     POST /research/resume                          │
│  │ SearchBar      │  │                              │                                                    │
│  └────────────────┘  │                              │   ┌────────────────────────────────────────────┐  │
│  ┌────┬────┬─────┐   │                              │   │  LangGraph StateGraph[ResearchState]       │  │
│  │ S  │ C  │ Syn │   │ <-- per-agent live stream    │   │                                            │  │
│  └────┴────┴─────┘   │                              │   │   Searcher → ask_for_refinement →          │  │
│  ┌────────────────┐  │  CustomEvent: awaiting_input │   │   await_refinement (interrupt) →           │  │
│  │ RefineInput    │  │  CustomEvent: citations      │   │   Critic → Synthesizer                     │  │
│  └────────────────┘  │  CustomEvent: confidence     │   └────────────────────────────────────────────┘  │
│  ┌────────────────┐  │                              │        │             │             │              │
│  │ ResultCard     │  │                              │        ▼             ▼             ▼              │
│  └────────────────┘  │                              │  ┌──────────┐  ┌───────────┐  ┌──────────┐       │
└──────────────────────┘                              │  │  Tavily  │  │  Gemini   │  │  mem0    │       │
        │                                             │  │  search  │  │  2.5 Flash│  │  cloud   │       │
        │  X-User-Id (localStorage)                   │  │          │  │  (stream) │  │  memory  │       │
        ▼                                             │  └──────────┘  └───────────┘  └──────────┘       │
   Persistent per-browser ID                          │                                                   │
                                                      │  truststore.inject_into_ssl()  (OS cert store)   │
                                                      └───────────────────────────────────────────────────┘
```

### Layer breakdown

- **Frontend** — Vite + React 19 + TypeScript + Tailwind v4. The `useResearchStream` hook fetches the SSE stream, parses events, and routes each `TextMessage*` event into a per-agent state slice keyed by `messageId` prefix (`searcher-…`, `critic-…`, `synthesizer-…`). `CustomEvent`s carry citations, confidence, and the awaiting-input prompt. Markdown rendering via `react-markdown` + `remark-gfm` with `@tailwindcss/typography` styling.
- **Backend** — FastAPI + LangGraph + langchain-google-genai + tavily-python + mem0ai. Each agent node pushes AG-UI events through `langgraph.config.get_stream_writer()`; `main.py` consumes `graph.astream(stream_mode=["custom","values","updates"])` and forwards events as SSE while watching the `updates` channel for `__interrupt__`.
- **HITL pause** — `langgraph.types.interrupt()` is called from `await_refinement_node` between Searcher and Critic. State is checkpointed via `InMemorySaver`. The browser receives a `CustomEvent(name="awaiting_input")`, the SSE closes (no `RUN_FINISHED`), and a follow-up `POST /research/resume` carries the user's refinement back via `Command(resume=...)`.

---

## Features

- **Live token streaming** for every agent. No buffering, no spinners.
- **Memory-aware follow-ups.** Pronouns like *"how does it work"* are resolved against your most-recent research before the Searcher hits Tavily, so web-search results stay on-topic.
- **Human-in-the-loop steering.** The graph pauses between agents; you can refine, skip, or accept-as-is. The refinement is woven into the Critic and Synthesizer prompts.
- **Citations as first-class data.** The synthesizer cites inline (`[1, 3]`); the UI rewrites those markers into anchor links that jump to the source list. Each source is a real Tavily URL, never hallucinated.
- **Confidence scoring.** The Synthesizer ends every answer with a `CONFIDENCE: N` line that's parsed and rendered as a colour-banded badge.
- **Graceful degradation.** When Tavily fails (missing key, SSL, quota, network), the Searcher streams a *"Web search unavailable"* banner and falls back to model knowledge.
- **Transient retries.** Gemini 429 / 500 / 503 / 504 errors are automatically retried once after 5 s — only when no chunks have yet been yielded, so partial output is never re-emitted.
- **Per-user persistent memory.** Browser keeps a `localStorage` UUID and sends it as `X-User-Id` on every request; mem0 keys memories by that.
- **Markdown rendering** in the final result with `@tailwindcss/typography`, including code blocks, lists, headings, bold/italic, and inline citations.
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
│   │   ├── searcher.py         memory-aware query rewrite + MCP search + Gemini summary
│   │   ├── steer.py            HITL ask_for_refinement + await_refinement nodes
│   │   ├── critic.py           gap analysis + one follow-up question
│   │   └── synthesizer.py      final answer + CONFIDENCE + citations
│   ├── mcp_servers/
│   │   └── tavily_server.py    FastMCP server — exposes tavily_search over stdio
│   └── tools/search.py         MCP client — spawns + drives the Tavily MCP server
├── frontend/
│   ├── src/
│   │   ├── App.tsx             SearchBar + 3 panels + RefineInput + ResultCard
│   │   ├── types.ts            AG-UI event union + StreamState + Citation
│   │   ├── hooks/useResearchStream.ts   fetch SSE parser, run() + resume()
│   │   └── components/         SearchBar / AgentPanel / RefineInput / ResultCard
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
