import { useCallback, useRef, useState } from "react";
import {
  AGENT_KEYS,
  INITIAL_STREAM_STATE,
  type AgentKey,
  type AgUiEvent,
  type AwaitingInput,
  type Citation,
  type StreamState,
} from "../types";

const RESEARCH_URL = "http://127.0.0.1:8000/research";
const RESUME_URL = "http://127.0.0.1:8000/research/resume";
const USER_ID_STORAGE_KEY = "live-research-intel.userId";

function agentKeyFrom(messageId: string): AgentKey | null {
  for (const key of AGENT_KEYS) {
    if (messageId.startsWith(`${key}-`)) return key;
  }
  return null;
}

function getOrCreateUserId(): string {
  try {
    const existing = localStorage.getItem(USER_ID_STORAGE_KEY);
    if (existing) return existing;
    const fresh = crypto.randomUUID();
    localStorage.setItem(USER_ID_STORAGE_KEY, fresh);
    return fresh;
  } catch {
    return crypto.randomUUID();
  }
}

function buildRunBody(question: string, threadId: string) {
  return {
    thread_id: threadId,
    run_id: crypto.randomUUID(),
    messages: [
      {
        id: crypto.randomUUID(),
        role: "user",
        content: question,
      },
    ],
    tools: [],
    context: [],
    forwarded_props: {},
    state: {},
  };
}

async function consumeSse(
  response: Response,
  setState: React.Dispatch<React.SetStateAction<StreamState>>,
) {
  if (!response.ok || !response.body) {
    throw new Error(`Backend returned ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let newlineIdx: number;
    while ((newlineIdx = buffer.indexOf("\n")) !== -1) {
      const rawLine = buffer.slice(0, newlineIdx).replace(/\r$/, "");
      buffer = buffer.slice(newlineIdx + 1);
      if (!rawLine.startsWith("data: ")) continue;
      const payload = rawLine.slice(6);
      if (!payload) continue;
      try {
        const event = JSON.parse(payload) as AgUiEvent;
        applyEvent(event, setState);
      } catch (err) {
        console.warn("Failed to parse SSE payload:", payload, err);
      }
    }
  }
}

export function useResearchStream() {
  const [state, setState] = useState<StreamState>(INITIAL_STREAM_STATE);
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(async (question: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const threadId = crypto.randomUUID();
    setState({
      ...INITIAL_STREAM_STATE,
      status: "running",
      threadId,
    });

    try {
      const response = await fetch(RESEARCH_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": getOrCreateUserId(),
        },
        body: JSON.stringify(buildRunBody(question, threadId)),
        signal: controller.signal,
      });
      await consumeSse(response, setState);
      // If no RUN_FINISHED arrived, awaitingInput will be set — leave
      // status="running" so the SearchBar stays disabled until resume.
      setState((prev) =>
        prev.awaitingInput ? prev : { ...prev, status: "done" },
      );
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      console.error("Stream failed:", err);
      setState((prev) => ({
        ...prev,
        status: "error",
        errorMessage: (err as Error).message ?? "Unknown error",
      }));
    }
  }, []);

  const resume = useCallback(
    async (refinement: string) => {
      // Snapshot thread id synchronously — React state in closure is fine
      // because resume is only callable when awaitingInput is set.
      const threadId = state.threadId;
      if (!threadId) {
        console.warn("resume() called without an active threadId");
        return;
      }

      // Clear the awaiting banner immediately and remember the refinement
      // (unless it's "skip" / empty) so the ResultCard can display it.
      const trimmed = refinement.trim();
      const appliedRefinement =
        trimmed && trimmed.toLowerCase() !== "skip" ? trimmed : null;
      setState((prev) => ({
        ...prev,
        awaitingInput: null,
        refinement: appliedRefinement,
      }));

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await fetch(RESUME_URL, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-User-Id": getOrCreateUserId(),
          },
          body: JSON.stringify({
            thread_id: threadId,
            user_input: refinement,
          }),
          signal: controller.signal,
        });
        await consumeSse(response, setState);
        setState((prev) =>
          prev.status === "running" ? { ...prev, status: "done" } : prev,
        );
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        console.error("Resume stream failed:", err);
        setState((prev) => ({
          ...prev,
          status: "error",
          errorMessage: (err as Error).message ?? "Unknown error",
        }));
      }
    },
    [state.threadId],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState(INITIAL_STREAM_STATE);
  }, []);

  return { state, run, resume, reset };
}

function applyEvent(
  event: AgUiEvent,
  setState: React.Dispatch<React.SetStateAction<StreamState>>,
) {
  switch (event.type) {
    case "RUN_STARTED":
      return;
    case "RUN_FINISHED":
      setState((prev) => ({ ...prev, status: "done" }));
      return;
    case "TEXT_MESSAGE_START": {
      const key = agentKeyFrom(event.messageId);
      if (!key) return;
      setState((prev) => ({
        ...prev,
        agents: {
          ...prev.agents,
          [key]: { status: "streaming", text: "" },
        },
      }));
      return;
    }
    case "TEXT_MESSAGE_CONTENT": {
      const key = agentKeyFrom(event.messageId);
      if (!key) return;
      setState((prev) => ({
        ...prev,
        agents: {
          ...prev.agents,
          [key]: {
            status: "streaming",
            text: prev.agents[key].text + event.delta,
          },
        },
      }));
      return;
    }
    case "TEXT_MESSAGE_END": {
      const key = agentKeyFrom(event.messageId);
      if (!key) return;
      setState((prev) => ({
        ...prev,
        agents: {
          ...prev.agents,
          [key]: { ...prev.agents[key], status: "done" },
        },
      }));
      return;
    }
    case "CUSTOM": {
      if (event.name === "citations" && Array.isArray(event.value)) {
        const citations = event.value as Citation[];
        setState((prev) => ({ ...prev, citations }));
      } else if (
        event.name === "confidence" &&
        typeof event.value === "number"
      ) {
        setState((prev) => ({ ...prev, confidence: event.value as number }));
      } else if (event.name === "awaiting_input") {
        const v = event.value as Partial<{
          prompt: string;
          question: string;
          search_preview: string;
        }>;
        const awaiting: AwaitingInput = {
          prompt: v?.prompt ?? "Refine the query before continuing?",
          question: v?.question ?? "",
          searchPreview: v?.search_preview ?? "",
        };
        setState((prev) => ({ ...prev, awaitingInput: awaiting }));
      }
      return;
    }
  }
}
