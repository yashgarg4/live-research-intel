import { useState, type FormEvent } from "react";
import type { AwaitingInput } from "../types";

interface RefineInputProps {
  awaiting: AwaitingInput;
  onSubmit: (refinement: string) => void;
}

export function RefineInput({ awaiting, onSubmit }: RefineInputProps) {
  const [value, setValue] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const submit = (refinement: string) => {
    if (submitted) return;
    setSubmitted(true);
    onSubmit(refinement);
  };

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const trimmed = value.trim();
    submit(trimmed || "skip");
  };

  return (
    <div className="rounded-2xl border border-indigo-500/40 bg-indigo-500/10 shadow-lg overflow-hidden">
      <div className="px-5 py-3 bg-indigo-500/15 border-b border-indigo-500/30 flex items-center gap-2">
        <span className="thinking-dot w-2 h-2 rounded-full bg-indigo-400" />
        <span className="text-sm font-semibold tracking-wide text-indigo-200 uppercase">
          Graph paused — your turn
        </span>
      </div>
      <div className="px-5 py-5 space-y-4">
        <div className="text-sm text-slate-200">{awaiting.prompt}</div>

        {awaiting.searchPreview && (
          <div className="rounded-lg bg-slate-950/50 border border-slate-800 px-3 py-2 text-xs text-slate-400 font-mono max-h-32 overflow-y-auto whitespace-pre-wrap">
            <span className="text-slate-500">Searcher output preview:</span>
            {"\n"}
            {awaiting.searchPreview}
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex gap-3">
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={submitted}
            placeholder="e.g., focus on enterprise use cases, add cost comparison, …"
            autoFocus
            className="flex-1 px-4 py-2.5 rounded-lg bg-slate-900/70 border border-slate-700 text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/60 focus:border-indigo-500 disabled:opacity-50 transition"
          />
          <button
            type="submit"
            disabled={submitted}
            className="px-5 py-2.5 rounded-lg bg-indigo-500 text-white font-medium hover:bg-indigo-400 active:bg-indigo-600 disabled:bg-slate-700 disabled:text-slate-400 transition"
          >
            {submitted ? "Resuming…" : value.trim() ? "Refine & continue" : "Continue as-is"}
          </button>
          <button
            type="button"
            onClick={() => submit("skip")}
            disabled={submitted}
            className="px-4 py-2.5 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 active:bg-slate-900 disabled:opacity-50 transition text-sm"
          >
            Skip
          </button>
        </form>
      </div>
    </div>
  );
}
