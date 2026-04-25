import { AgentPanel } from "./components/AgentPanel";
import { RefineInput } from "./components/RefineInput";
import { ResultCard } from "./components/ResultCard";
import { SearchBar } from "./components/SearchBar";
import { useResearchStream } from "./hooks/useResearchStream";
import { AGENT_KEYS } from "./types";

function App() {
  const { state, run, resume } = useResearchStream();

  const isRunning = state.status === "running";
  const synthText = state.agents.synthesizer.text;
  const showResult =
    state.agents.synthesizer.status === "done" && synthText.length > 0;

  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-slate-800/70 bg-slate-950/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 md:px-6 py-5 flex flex-col gap-4">
          <div className="flex items-baseline justify-between gap-3">
            <div>
              <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-50">
                Live Research Intelligence
              </h1>
              <p className="text-sm text-slate-400 mt-1">
                Watch three specialist agents think, critique, and synthesize in
                real time.
              </p>
            </div>
            <StatusPill status={state.status} />
          </div>
          <SearchBar onSubmit={run} disabled={isRunning} />
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 md:px-6 py-6 md:py-8 flex flex-col gap-6">
        <section className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-5">
          {AGENT_KEYS.map((key) => (
            <AgentPanel key={key} agent={key} state={state.agents[key]} />
          ))}
        </section>

        {state.awaitingInput && (
          <RefineInput
            awaiting={state.awaitingInput}
            onSubmit={resume}
          />
        )}

        {showResult && (
          <ResultCard
            synthText={synthText}
            citations={state.citations}
            confidence={state.confidence}
            refinement={state.refinement}
          />
        )}

        {state.status === "error" && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 text-rose-200 px-4 py-3 text-sm">
            Stream failed: {state.errorMessage ?? "unknown error"}
          </div>
        )}

        {state.status === "idle" && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 text-slate-400 px-5 py-6 text-sm text-center">
            Type a question above to start a research run. The three panels will
            stream as each agent produces output.
          </div>
        )}
      </main>

      <footer className="border-t border-slate-800/70 text-xs text-slate-500 py-4 text-center">
        AG-UI · LangGraph · Gemini 2.5 Flash · Tavily
      </footer>
    </div>
  );
}

function StatusPill({
  status,
}: {
  status: "idle" | "running" | "done" | "error";
}) {
  const label =
    status === "running"
      ? "Streaming"
      : status === "done"
        ? "Ready"
        : status === "error"
          ? "Error"
          : "Idle";
  const cls =
    status === "running"
      ? "bg-indigo-500/15 text-indigo-300 border-indigo-500/40"
      : status === "done"
        ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
        : status === "error"
          ? "bg-rose-500/15 text-rose-300 border-rose-500/40"
          : "bg-slate-700/40 text-slate-400 border-slate-700";
  return (
    <span
      className={`hidden md:inline-flex items-center gap-2 px-3 py-1 rounded-full border text-xs font-medium ${cls}`}
    >
      {status === "running" && (
        <span className="thinking-dot w-1.5 h-1.5 rounded-full bg-indigo-400" />
      )}
      {label}
    </span>
  );
}

export default App;
