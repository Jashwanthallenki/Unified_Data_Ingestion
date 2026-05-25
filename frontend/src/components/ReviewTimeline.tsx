import type { ReviewLogEntry } from "../api/types";
import { formatDateTime, humanize } from "../lib/format";
import { EmptyState } from "./States";

export default function ReviewTimeline({
  logs,
  createdAt,
  flags,
}: {
  logs: ReviewLogEntry[];
  createdAt: string;
  flags: string[];
}) {
  const synthetic = [
    { id: "created", label: "Created from batch", date: createdAt, detail: "Normalized activity record was created during ingestion." },
    ...(flags.includes("LLM_SUGGESTED_FIELD")
      ? [{ id: "ai", label: "AI suggestion available", date: createdAt, detail: "Groq suggestion exists and needs analyst decision." }]
      : []),
    ...(flags.some((flag) => flag.includes("SUSPICIOUS") || flag.includes("SPIKE"))
      ? [{ id: "flagged", label: "Flagged for analyst attention", date: createdAt, detail: "A suspicious or outlier signal was detected." }]
      : []),
  ];

  if (!logs.length && synthetic.length === 1) {
    return (
      <EmptyState
        title="No analyst actions yet."
        message="The review history will show approvals, rejections, overrides, AI decisions, and audit locks."
      />
    );
  }

  return (
    <ol className="space-y-4">
      {synthetic.map((event) => (
        <li key={event.id} className="relative border-l-2 border-slate-200 pl-4">
          <div className="text-sm font-semibold text-slate-900">{event.label}</div>
          <div className="text-xs text-slate-500">{formatDateTime(event.date)}</div>
          <p className="mt-1 text-sm text-slate-600">{event.detail}</p>
        </li>
      ))}
      {logs.map((log) => (
        <li key={log.id} className="relative border-l-2 border-emerald-200 pl-4">
          <div className="text-sm font-semibold text-slate-900">{humanize(log.action)}</div>
          <div className="text-xs text-slate-500">
            {formatDateTime(log.created_at)}
            {log.reviewer_username ? ` by ${log.reviewer_username}` : ""}
          </div>
          {log.comment ? <p className="mt-1 text-sm text-slate-600">{log.comment}</p> : null}
        </li>
      ))}
    </ol>
  );
}
