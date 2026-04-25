import type { ToolCall } from "../types";

interface ToolCallStripProps {
  calls: ToolCall[];
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function statusStyles(status: ToolCall["status"]) {
  switch (status) {
    case "running":
      return {
        wrap: "border-indigo-500/40 bg-indigo-500/10 text-indigo-200",
        dot: "bg-indigo-400 animate-pulse",
        label: "running…",
        labelCls: "text-indigo-300",
      };
    case "done":
      return {
        wrap: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
        dot: "bg-emerald-400",
        label: "done",
        labelCls: "text-emerald-300",
      };
    case "error":
      return {
        wrap: "border-rose-500/40 bg-rose-500/10 text-rose-200",
        dot: "bg-rose-400",
        label: "failed",
        labelCls: "text-rose-300",
      };
  }
}

export function ToolCallStrip({ calls }: ToolCallStripProps) {
  if (calls.length === 0) return null;
  return (
    <div className="mb-3 flex flex-wrap gap-2">
      {calls.map((c) => {
        const s = statusStyles(c.status);
        const queryArg =
          typeof c.args.query === "string" ? c.args.query : "";
        return (
          <div
            key={c.id}
            className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-full border text-xs ${s.wrap}`}
            title={
              c.error
                ? `${c.toolName}(${queryArg}) → error: ${c.error}`
                : `${c.toolName}(${queryArg})`
            }
          >
            <span
              className={`inline-block w-1.5 h-1.5 rounded-full ${s.dot}`}
              aria-hidden="true"
            />
            <span className="font-mono text-[11px] tracking-tight">
              {c.toolName}
            </span>
            <span className={`text-[10px] uppercase tracking-wider ${s.labelCls}`}>
              {s.label}
            </span>
            {c.status !== "running" && (
              <span className="text-[10px] text-slate-400 font-mono">
                {c.error
                  ? "error"
                  : `${c.sourceCount ?? 0} source${c.sourceCount === 1 ? "" : "s"}`}
                {c.durationMs !== null && ` · ${formatDuration(c.durationMs)}`}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
