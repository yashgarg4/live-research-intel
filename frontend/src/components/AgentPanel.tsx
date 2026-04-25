import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AgentKey, AgentState, ToolCall } from "../types";
import { ToolCallStrip } from "./ToolCallStrip";

interface AgentPanelProps {
  agent: AgentKey;
  state: AgentState;
  toolCalls?: ToolCall[];
}

interface Styling {
  title: string;
  subtitle: string;
  headerBg: string;
  headerText: string;
  accentBar: string;
  dot: string;
}

const STYLES: Record<AgentKey, Styling> = {
  searcher: {
    title: "Searcher",
    subtitle: "Web research + summary",
    headerBg: "bg-teal-500/10 border-teal-500/30",
    headerText: "text-teal-300",
    accentBar: "bg-teal-500",
    dot: "bg-teal-400",
  },
  critic: {
    title: "Critic",
    subtitle: "Gaps, biases, follow-ups",
    headerBg: "bg-amber-500/10 border-amber-500/30",
    headerText: "text-amber-300",
    accentBar: "bg-amber-500",
    dot: "bg-amber-400",
  },
  synthesizer: {
    title: "Synthesizer",
    subtitle: "Final cited answer",
    headerBg: "bg-rose-500/10 border-rose-500/30",
    headerText: "text-rose-300",
    accentBar: "bg-rose-500",
    dot: "bg-rose-400",
  },
};

export function AgentPanel({ agent, state, toolCalls }: AgentPanelProps) {
  const s = STYLES[agent];
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [state.text]);

  const hasTools = (toolCalls?.length ?? 0) > 0;

  return (
    <div className="flex flex-col min-h-0 rounded-2xl bg-slate-900/80 border border-slate-800 shadow-lg overflow-hidden">
      <div className={`border-b ${s.headerBg} px-4 py-3 flex items-center gap-3`}>
        <div className={`w-1 h-7 rounded-full ${s.accentBar}`} />
        <div className="flex-1 min-w-0">
          <div className={`font-semibold tracking-tight ${s.headerText}`}>
            {s.title}
          </div>
          <div className="text-xs text-slate-400">{s.subtitle}</div>
        </div>
        <StatusBadge status={state.status} dotClass={s.dot} />
      </div>
      <div
        ref={scrollRef}
        className="flex-1 min-h-[260px] max-h-[520px] overflow-y-auto p-4"
      >
        {hasTools && <ToolCallStrip calls={toolCalls ?? []} />}
        {state.text ? (
          <div
            className="prose prose-invert prose-sm max-w-none
                       prose-headings:text-slate-100 prose-headings:font-semibold
                       prose-strong:text-slate-50
                       prose-a:text-indigo-300 prose-a:no-underline hover:prose-a:underline
                       prose-code:text-amber-300 prose-code:bg-slate-800/60
                       prose-code:px-1 prose-code:py-0.5 prose-code:rounded
                       prose-code:before:content-[''] prose-code:after:content-['']
                       prose-li:marker:text-slate-500
                       prose-p:my-2 prose-li:my-0.5
                       prose-hr:border-slate-700"
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {state.text}
            </ReactMarkdown>
          </div>
        ) : state.status === "done" ? (
          <span className="text-rose-400/80 italic text-sm">
            No output — the model likely hit a rate limit or transient error.
            Try the question again.
          </span>
        ) : state.status === "streaming" ? (
          <span className="text-slate-500 italic text-sm">Thinking…</span>
        ) : (
          <span className="text-slate-500 italic text-sm">
            Waiting for upstream agent…
          </span>
        )}
      </div>
    </div>
  );
}

function StatusBadge({
  status,
  dotClass,
}: {
  status: AgentState["status"];
  dotClass: string;
}) {
  if (status === "done") {
    return (
      <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-400">
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className="w-4 h-4"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M16.704 5.29a1 1 0 010 1.42l-7.5 7.5a1 1 0 01-1.42 0l-3.5-3.5a1 1 0 111.42-1.42L8.5 12.09l6.79-6.8a1 1 0 011.414 0z"
            clipRule="evenodd"
          />
        </svg>
        Done
      </div>
    );
  }
  if (status === "streaming") {
    return (
      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-200">
        <span className={`thinking-dot w-2 h-2 rounded-full ${dotClass}`} />
        Thinking
      </div>
    );
  }
  return (
    <div className="text-xs font-medium text-slate-500">Idle</div>
  );
}
