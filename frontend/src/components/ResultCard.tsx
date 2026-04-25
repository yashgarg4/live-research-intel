import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation } from "../types";

interface ResultCardProps {
  synthText: string;
  citations: Citation[];
  confidence: number | null;
  refinement: string | null;
}

const CONFIDENCE_RE = /CONFIDENCE:\s*(\d{1,3})/i;
const INLINE_CITE_RE = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

function stripTrailingConfidence(text: string): string {
  return text.replace(CONFIDENCE_RE, "").trimEnd();
}

function hostnameOrUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function confidenceBand(score: number) {
  if (score >= 70)
    return {
      label: "High",
      cls: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
    };
  if (score >= 40)
    return {
      label: "Moderate",
      cls: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    };
  return {
    label: "Low",
    cls: "bg-rose-500/20 text-rose-300 border-rose-500/40",
  };
}

// Rewrite `[1, 3]` inline markers into markdown links that jump to citation list item below. Only keeps indices that actually exist in the
// citations list so broken markers render as plain text.
function linkifyCitations(text: string, citations: Citation[]): string {
  if (citations.length === 0) return text;
  const valid = new Set(citations.map((c) => c.index));
  return text.replace(INLINE_CITE_RE, (_match, nums: string) => {
    const parts = nums
      .split(",")
      .map((n) => parseInt(n.trim(), 10))
      .filter((n) => Number.isFinite(n) && valid.has(n));
    if (parts.length === 0) return _match;
    return parts.map((n) => `[\\[${n}\\]](#citation-${n})`).join(", ");
  });
}

export function ResultCard({
  synthText,
  citations,
  confidence,
  refinement,
}: ResultCardProps) {
  const body = useMemo(
    () => linkifyCitations(stripTrailingConfidence(synthText), citations),
    [synthText, citations],
  );

  return (
    <div className="rounded-2xl bg-gradient-to-br from-slate-900 to-slate-900/60 border border-slate-700 shadow-xl p-6 md:p-8">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
        <div>
          <div className="text-xs uppercase tracking-widest text-slate-400 mb-1">
            Final synthesized answer
          </div>
          <h2 className="text-xl md:text-2xl font-semibold text-slate-100">
            Result
          </h2>
        </div>
        {confidence !== null && <ConfidenceBadge score={confidence} />}
      </div>

      {refinement && (
        <div className="mb-6 inline-flex items-start gap-2 px-3 py-2 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-200 text-sm max-w-full">
          <svg
            viewBox="0 0 20 20"
            fill="currentColor"
            className="w-4 h-4 mt-0.5 text-indigo-300 shrink-0"
            aria-hidden="true"
          >
            <path d="M7.5 2a5.5 5.5 0 014.383 8.823l4.147 4.147a1 1 0 11-1.414 1.414l-4.147-4.147A5.5 5.5 0 117.5 2zm0 2a3.5 3.5 0 100 7 3.5 3.5 0 000-7z" />
          </svg>
          <div>
            <span className="text-xs uppercase tracking-wider text-indigo-300/80 mr-2">
              Steered with
            </span>
            <span className="font-medium break-words">{refinement}</span>
          </div>
        </div>
      )}

      <div
        className="prose prose-invert prose-sm md:prose-base max-w-none
                   prose-headings:text-slate-100 prose-strong:text-slate-50
                   prose-a:text-indigo-300 prose-a:no-underline
                   hover:prose-a:text-indigo-200 hover:prose-a:underline
                   prose-code:text-amber-300 prose-code:bg-slate-800/60
                   prose-code:px-1 prose-code:py-0.5 prose-code:rounded
                   prose-code:before:content-[''] prose-code:after:content-['']
                   prose-li:marker:text-slate-500"
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
      </div>

      {citations.length > 0 && (
        <div className="mt-8 border-t border-slate-800 pt-6">
          <div className="text-sm font-semibold text-slate-300 mb-3">
            Citations
          </div>
          <ol className="space-y-1.5 text-sm">
            {citations.map((c) => (
              <li
                id={`citation-${c.index}`}
                key={c.index}
                className="flex gap-2 scroll-mt-24 target:bg-indigo-500/15 target:ring-1 target:ring-indigo-500/40 rounded-md transition-colors"
              >
                <span className="text-slate-500 font-mono shrink-0">
                  [{c.index}]
                </span>
                {c.url ? (
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-indigo-300 hover:text-indigo-200 hover:underline break-all"
                    title={c.url}
                  >
                    {c.title || hostnameOrUrl(c.url)}
                  </a>
                ) : (
                  <span className="text-slate-400">{c.title}</span>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function ConfidenceBadge({ score }: { score: number }) {
  const band = confidenceBand(score);
  return (
    <div
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm font-medium ${band.cls}`}
    >
      <span className="text-xs uppercase tracking-wider opacity-80">
        Confidence
      </span>
      <span className="font-mono text-base">{score}</span>
      <span className="text-xs opacity-70">{band.label}</span>
    </div>
  );
}
