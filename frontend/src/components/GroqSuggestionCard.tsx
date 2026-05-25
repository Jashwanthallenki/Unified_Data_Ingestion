import type { GroqSuggestResponse, LlmSuggestion } from "../api/types";
import { formatNumber, humanize } from "../lib/format";
import { EmptyState } from "./States";

export default function GroqSuggestionCard({
  suggestions,
  result,
  busy,
  locked,
  onRequest,
  onAccept,
  onReject,
}: {
  suggestions: LlmSuggestion[];
  result: GroqSuggestResponse | null;
  busy: boolean;
  locked: boolean;
  onRequest: () => void;
  onAccept: (field: string) => void;
  onReject: (field: string) => void;
}) {
  if (result && !result.ok) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 shadow-sm">
        <h2 className="text-base font-semibold text-amber-900">Groq suggestion failed, but this row is still available for manual review.</h2>
        <p className="mt-2 text-sm text-amber-800">{result.error || "No AI suggestion could be created."}</p>
      </div>
    );
  }

  if (!suggestions.length) {
    return (
      <EmptyState
        title="No AI suggestions were needed for this record."
        message="You can request a Groq suggestion for low or medium confidence rows, but analyst review always remains available."
        action={!locked ? <button className="btn" disabled={busy} onClick={onRequest}>Request Groq suggestion</button> : null}
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-purple-200 bg-purple-50 p-4 text-sm text-purple-900">
        AI suggestions are not final until accepted by an analyst.
      </div>
      {suggestions.map((suggestion) => (
        <article key={suggestion.field} className="card border-purple-200 p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="text-xs font-semibold uppercase text-slate-500">Suggested field</div>
              <h3 className="mt-1 text-base font-semibold text-slate-950">{humanize(suggestion.field)}</h3>
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                <div>
                  <div className="text-xs font-semibold uppercase text-slate-500">Suggested value</div>
                  <div className="mt-1 text-sm font-semibold text-slate-900">{String(suggestion.suggested_value)}</div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase text-slate-500">Confidence</div>
                  <div className="mt-1 text-sm font-semibold text-slate-900">{formatNumber(suggestion.confidence * 100, 0)}%</div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase text-slate-500">Method</div>
                  <div className="mt-1 text-sm font-semibold text-slate-900">{humanize(suggestion.method)}</div>
                </div>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">{suggestion.reason}</p>
            </div>
            {!locked ? (
              <div className="flex shrink-0 gap-2">
                <button className="btn-primary" disabled={busy} onClick={() => onAccept(suggestion.field)}>Accept</button>
                <button className="btn" disabled={busy} onClick={() => onReject(suggestion.field)}>Reject</button>
              </div>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}
