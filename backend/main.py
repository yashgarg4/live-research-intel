"""FastAPI app exposing the AG-UI SSE streaming endpoints.

Two endpoints:

* ``POST /research``          — starts a run. Runs Searcher, then pauses at
                                 the HITL steer node and closes the stream
                                 with a ``CustomEvent(awaiting_input)``.
                                 No ``RUN_FINISHED`` is emitted in this
                                 segment — the run is still live, paused in
                                 the checkpointer under its ``thread_id``.
* ``POST /research/resume``   — resumes a paused thread with the user's
                                 refinement (or "skip"). Streams the
                                 remaining events (Critic, Synthesizer,
                                 citations, confidence, ``RUN_FINISHED``),
                                 then persists memory.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from ag_ui.core import (
    BaseEvent,
    CustomEvent,
    EventType,
    RunAgentInput,
    RunFinishedEvent,
    RunStartedEvent,
)
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from backend.graph import graph
from backend.memory import get_context, get_most_recent, save_research

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("live-research-intel")

app = FastAPI(title="Live Research Intelligence", version="0.5.0")

# CORS: with allow_credentials=True the browser ignores wildcards, so every
# custom header we send from the SPA has to be listed explicitly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-User-Id"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# In-process bookkeeping for paused runs. Lets /research/resume recover the
# user_id (which was on a request header, not in graph state) and the run_id
# (which AG-UI events are keyed on). Keyed by thread_id.
_pending_runs: dict[str, dict[str, str]] = {}


async def _run_graph_and_stream(
    *,
    input_or_command: Any,
    thread_id: str,
    run_id: str,
    user_id: str,
    encoder: EventEncoder,
    emit_run_started: bool,
):
    """Shared core: drive ``graph.astream`` and forward events as SSE.

    Handles three stream modes at once:
      - ``custom``  → AG-UI event from a node's stream writer, re-encode.
      - ``values``  → full state snapshot, tracked for post-run handling.
      - ``updates`` → per-node update dicts. When LangGraph hits an
                      ``interrupt()`` it emits a ``__interrupt__`` key here,
                      which is our signal to close the SSE without a
                      ``RUN_FINISHED`` so the browser knows input is needed.
    """
    config = {"configurable": {"thread_id": thread_id}}

    if emit_run_started:
        logger.info(
            "Run started user=%s thread=%s run=%s", user_id, thread_id, run_id
        )
        yield encoder.encode(
            RunStartedEvent(
                type=EventType.RUN_STARTED,
                thread_id=thread_id,
                run_id=run_id,
            )
        )
    else:
        logger.info(
            "Run resumed user=%s thread=%s run=%s", user_id, thread_id, run_id
        )

    final_values: dict[str, Any] = {}
    interrupted = False

    try:
        async for mode, data in graph.astream(
            input_or_command,
            config=config,
            stream_mode=["custom", "values", "updates"],
        ):
            if mode == "custom":
                if isinstance(data, BaseEvent):
                    yield encoder.encode(data)
                else:
                    logger.warning(
                        "Custom stream payload was not an AG-UI event: %r",
                        type(data),
                    )
            elif mode == "values":
                if isinstance(data, dict):
                    final_values = data
            elif mode == "updates":
                if isinstance(data, dict) and "__interrupt__" in data:
                    interrupted = True
                    logger.info(
                        "Graph paused at interrupt — awaiting user input, "
                        "thread=%s",
                        thread_id,
                    )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Graph execution failed: %s", exc)

    if interrupted:
        # Remember the mapping so /research/resume can recover user/run ids.
        _pending_runs[thread_id] = {"user_id": user_id, "run_id": run_id}
        # No RUN_FINISHED — the run is still alive, paused in the checkpointer.
        return

    # Terminal segment: emit citations, confidence, save memory, RUN_FINISHED.
    logger.info(
        "Graph final state keys=%s confidence=%s citations=%d",
        list(final_values.keys()),
        final_values.get("confidence"),
        len(final_values.get("citations", []) or []),
    )

    citations = final_values.get("citations", []) or []
    if citations:
        yield encoder.encode(
            CustomEvent(
                type=EventType.CUSTOM,
                name="citations",
                value=citations,
            )
        )

    confidence = final_values.get("confidence")
    if confidence is not None:
        yield encoder.encode(
            CustomEvent(
                type=EventType.CUSTOM,
                name="confidence",
                value=int(confidence),
            )
        )

    final_answer = final_values.get("final_answer", "") or ""
    question = final_values.get("question", "") or ""
    question_to_save = (
        final_values.get("resolved_question") or question
    ).strip()
    if question_to_save and final_answer:
        await save_research(user_id, question_to_save, final_answer)

    _pending_runs.pop(thread_id, None)

    logger.info(
        "Run finished user=%s thread=%s run=%s", user_id, thread_id, run_id
    )
    yield encoder.encode(
        RunFinishedEvent(
            type=EventType.RUN_FINISHED,
            thread_id=thread_id,
            run_id=run_id,
        )
    )


@app.post("/research")
async def research(request: Request) -> StreamingResponse:
    body = await request.json()
    run_input = RunAgentInput(**body)
    user_id = request.headers.get("X-User-Id") or "anonymous"
    encoder = EventEncoder()

    thread_id = run_input.thread_id or str(uuid.uuid4())
    run_id = run_input.run_id or str(uuid.uuid4())

    question = ""
    if run_input.messages:
        last = run_input.messages[-1]
        content = getattr(last, "content", None)
        if content:
            question = content

    memory_context = await get_context(user_id, question)
    recent_memory = await get_most_recent(user_id)

    initial_state: dict[str, Any] = {
        "messages": [],
        "question": question,
        "memory_context": memory_context,
        "recent_memory": recent_memory,
    }

    return StreamingResponse(
        _run_graph_and_stream(
            input_or_command=initial_state,
            thread_id=thread_id,
            run_id=run_id,
            user_id=user_id,
            encoder=encoder,
            emit_run_started=True,
        ),
        media_type="text/event-stream",
    )


@app.post("/research/resume")
async def research_resume(request: Request) -> StreamingResponse:
    body = await request.json()
    thread_id = (body.get("thread_id") or "").strip()
    user_input = body.get("user_input")

    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id required")

    pending = _pending_runs.get(thread_id)
    if not pending:
        raise HTTPException(
            status_code=404,
            detail=f"No paused run found for thread_id={thread_id}",
        )

    # Prefer the browser's X-User-Id (it should match what was stored but the
    # stored copy is the source of truth when the header is missing).
    user_id = request.headers.get("X-User-Id") or pending["user_id"]
    run_id = pending["run_id"]
    encoder = EventEncoder()

    resume_value = user_input if isinstance(user_input, str) else ""

    return StreamingResponse(
        _run_graph_and_stream(
            input_or_command=Command(resume=resume_value),
            thread_id=thread_id,
            run_id=run_id,
            user_id=user_id,
            encoder=encoder,
            emit_run_started=False,
        ),
        media_type="text/event-stream",
    )
