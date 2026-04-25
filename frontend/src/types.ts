// AG-UI event shapes we care about from the backend /research SSE stream.
// The backend emits only the subset below; all other AG-UI event types are ignored.

export type AgentKey = "searcher" | "critic" | "synthesizer";

export interface RunStartedEvent {
  type: "RUN_STARTED";
  threadId: string;
  runId: string;
}

export interface RunFinishedEvent {
  type: "RUN_FINISHED";
  threadId: string;
  runId: string;
}

export interface TextMessageStartEvent {
  type: "TEXT_MESSAGE_START";
  messageId: string;
  role?: string;
}

export interface TextMessageContentEvent {
  type: "TEXT_MESSAGE_CONTENT";
  messageId: string;
  delta: string;
}

export interface TextMessageEndEvent {
  type: "TEXT_MESSAGE_END";
  messageId: string;
}

export interface CustomEvent<T = unknown> {
  type: "CUSTOM";
  name: string;
  value: T;
}

export type AgUiEvent =
  | RunStartedEvent
  | RunFinishedEvent
  | TextMessageStartEvent
  | TextMessageContentEvent
  | TextMessageEndEvent
  | CustomEvent;

export interface Citation {
  index: number;
  title: string;
  url: string;
}

export interface ToolCall {
  id: string;
  toolName: string;
  args: Record<string, unknown>;
  status: "running" | "done" | "error";
  sourceCount: number | null;
  error: string | null;
  durationMs: number | null;
  parentMessageId: string | null;
}

export interface AgentState {
  status: "idle" | "streaming" | "done";
  text: string;
}

export interface AwaitingInput {
  prompt: string;
  question: string;
  searchPreview: string;
}

export interface StreamState {
  status: "idle" | "running" | "done" | "error";
  agents: Record<AgentKey, AgentState>;
  citations: Citation[];
  confidence: number | null;
  threadId: string | null;
  awaitingInput: AwaitingInput | null;
  refinement: string | null; // set when user submits a non-"skip" refinement
  toolCalls: ToolCall[];
  errorMessage?: string;
}

export const INITIAL_STREAM_STATE: StreamState = {
  status: "idle",
  agents: {
    searcher: { status: "idle", text: "" },
    critic: { status: "idle", text: "" },
    synthesizer: { status: "idle", text: "" },
  },
  citations: [],
  confidence: null,
  threadId: null,
  awaitingInput: null,
  refinement: null,
  toolCalls: [],
};

export const AGENT_KEYS: AgentKey[] = ["searcher", "critic", "synthesizer"];
