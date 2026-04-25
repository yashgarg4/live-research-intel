import { Fragment } from "react";
import type { StreamState } from "../types";

type NodeStatus = "pending" | "active" | "done";

interface NodeDef {
  id: "searcher" | "steer" | "critic" | "synthesizer";
  label: string;
  sublabel: string;
  // Per-node accent that mirrors each agent panel's colour scheme.
  accent: {
    activeBg: string;
    activeBorder: string;
    activeText: string;
    activeDot: string;
    doneText: string;
  };
}

const NODES: NodeDef[] = [
  {
    id: "searcher",
    label: "Searcher",
    sublabel: "web + wiki",
    accent: {
      activeBg: "bg-teal-500/15",
      activeBorder: "border-teal-500/60",
      activeText: "text-teal-200",
      activeDot: "bg-teal-400",
      doneText: "text-teal-300",
    },
  },
  {
    id: "steer",
    label: "Steer",
    sublabel: "HITL pause",
    accent: {
      activeBg: "bg-indigo-500/15",
      activeBorder: "border-indigo-500/60",
      activeText: "text-indigo-200",
      activeDot: "bg-indigo-400",
      doneText: "text-indigo-300",
    },
  },
  {
    id: "critic",
    label: "Critic",
    sublabel: "gaps + bias",
    accent: {
      activeBg: "bg-amber-500/15",
      activeBorder: "border-amber-500/60",
      activeText: "text-amber-200",
      activeDot: "bg-amber-400",
      doneText: "text-amber-300",
    },
  },
  {
    id: "synthesizer",
    label: "Synthesizer",
    sublabel: "final answer",
    accent: {
      activeBg: "bg-rose-500/15",
      activeBorder: "border-rose-500/60",
      activeText: "text-rose-200",
      activeDot: "bg-rose-400",
      doneText: "text-rose-300",
    },
  },
];

function computeStatuses(
  state: StreamState,
): Record<NodeDef["id"], NodeStatus> {
  const searcher = state.agents.searcher.status;
  const critic = state.agents.critic.status;
  const synth = state.agents.synthesizer.status;
  const awaiting = state.awaitingInput !== null;

  const searcherStatus: NodeStatus =
    searcher === "idle"
      ? "pending"
      : searcher === "streaming"
        ? "active"
        : "done";

  // Steer is active iff the graph is paused waiting for input. It transitions
  // to "done" once the Critic starts (i.e. the user resumed). Stays "pending"
  // before any Searcher activity.
  let steerStatus: NodeStatus = "pending";
  if (awaiting) {
    steerStatus = "active";
  } else if (critic !== "idle") {
    steerStatus = "done";
  } else if (searcher === "done") {
    // Searcher finished, awaiting_input not yet observed (event in flight) —
    // show steer as active so the bar doesn't blank between transitions.
    steerStatus = "active";
  }

  const criticStatus: NodeStatus =
    critic === "idle"
      ? "pending"
      : critic === "streaming"
        ? "active"
        : "done";

  const synthStatus: NodeStatus =
    synth === "idle"
      ? "pending"
      : synth === "streaming"
        ? "active"
        : "done";

  return {
    searcher: searcherStatus,
    steer: steerStatus,
    critic: criticStatus,
    synthesizer: synthStatus,
  };
}

export function GraphViz({ state }: { state: StreamState }) {
  const statuses = computeStatuses(state);

  return (
    <section
      aria-label="Graph topology"
      className="rounded-2xl border border-slate-800 bg-slate-900/50 px-4 py-4 md:px-6 md:py-5"
    >
      <div className="flex items-center justify-between mb-3 gap-3">
        <div className="text-xs uppercase tracking-widest text-slate-500">
          LangGraph topology
        </div>
        <div className="hidden md:block text-[11px] text-slate-500 font-mono truncate">
          searcher → ask_for_refinement → await_refinement → critic →
          synthesizer
        </div>
      </div>

      <ol className="flex flex-col md:flex-row md:items-stretch gap-2 md:gap-0">
        {NODES.map((node, i) => (
          <Fragment key={node.id}>
            <li className="md:flex-1 min-w-0">
              <NodePill node={node} status={statuses[node.id]} />
            </li>
            {i < NODES.length - 1 && (
              <li
                aria-hidden="true"
                className="flex items-center justify-center text-slate-600 md:px-1"
              >
                {/* desktop: right arrow; mobile: down chevron */}
                <svg
                  viewBox="0 0 16 16"
                  fill="currentColor"
                  className="w-4 h-4 hidden md:block"
                >
                  <path d="M6 4l4 4-4 4V4z" />
                </svg>
                <svg
                  viewBox="0 0 16 16"
                  fill="currentColor"
                  className="w-4 h-4 md:hidden"
                >
                  <path d="M4 6l4 4 4-4H4z" />
                </svg>
              </li>
            )}
          </Fragment>
        ))}
      </ol>
    </section>
  );
}

function NodePill({ node, status }: { node: NodeDef; status: NodeStatus }) {
  const base =
    "w-full min-w-0 flex items-center gap-3 px-3 py-2.5 rounded-xl border transition-colors";

  let wrapCls: string;
  let dotCls: string;
  let labelCls: string;
  let iconWrapCls: string;
  let showCheck = false;

  if (status === "active") {
    wrapCls = `${base} ${node.accent.activeBg} ${node.accent.activeBorder} shadow-md`;
    dotCls = `${node.accent.activeDot} thinking-dot`;
    labelCls = `font-semibold ${node.accent.activeText}`;
    iconWrapCls = "bg-slate-950/60";
  } else if (status === "done") {
    wrapCls = `${base} bg-slate-900/70 border-emerald-500/40`;
    dotCls = "bg-emerald-400";
    labelCls = `font-semibold ${node.accent.doneText}`;
    iconWrapCls = "bg-emerald-500/20 text-emerald-300";
    showCheck = true;
  } else {
    wrapCls = `${base} bg-slate-900/40 border-slate-800`;
    dotCls = "bg-slate-700";
    labelCls = "font-medium text-slate-400";
    iconWrapCls = "bg-slate-800/70 text-slate-600";
  }

  return (
    <div className={wrapCls}>
      <span
        className={`shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-full ${iconWrapCls}`}
        aria-hidden="true"
      >
        {showCheck ? (
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
            <path
              fillRule="evenodd"
              d="M16.704 5.29a1 1 0 010 1.42l-7.5 7.5a1 1 0 01-1.42 0l-3.5-3.5a1 1 0 111.42-1.42L8.5 12.09l6.79-6.8a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
        ) : (
          <span className={`w-2 h-2 rounded-full ${dotCls}`} />
        )}
      </span>
      <div className="min-w-0">
        <div className={`text-sm leading-tight truncate ${labelCls}`}>
          {node.label}
        </div>
        <div className="text-[11px] text-slate-500 truncate">
          {node.sublabel}
        </div>
      </div>
    </div>
  );
}
