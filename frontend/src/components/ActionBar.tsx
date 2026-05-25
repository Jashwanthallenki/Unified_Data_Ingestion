import { useState } from "react";
import type { NormalizedActivityDetail } from "../api/types";

const overrideFields = [
  "activity_subtype",
  "facility_name",
  "facility_country",
  "scope",
  "scope_category",
  "calculation_method",
  "emission_method",
];

export default function ActionBar({
  activity,
  busy,
  onApprove,
  onReject,
  onClarify,
  onOverride,
  onLock,
}: {
  activity: NormalizedActivityDetail;
  busy: boolean;
  onApprove: (comment?: string) => void;
  onReject: (comment: string) => void;
  onClarify: (comment: string) => void;
  onOverride: (field: string, value: string, comment: string) => void;
  onLock: () => void;
}) {
  const [comment, setComment] = useState("");
  const [field, setField] = useState("activity_subtype");
  const [value, setValue] = useState("");
  const locked = !!activity.locked_at || activity.review_status === "LOCKED";
  const canLock = activity.review_status === "APPROVED" && !locked;
  const currentValue = (activity as unknown as Record<string, unknown>)[field];

  return (
    <div className="sticky bottom-0 z-10 -mx-4 border-t border-slate-200 bg-white/95 p-4 shadow-2xl backdrop-blur sm:-mx-6 lg:-mx-8">
      <div className="mx-auto max-w-7xl space-y-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <label className="min-w-0 flex-1">
            <span className="text-xs font-semibold uppercase text-slate-500">Review comment</span>
            <textarea
              rows={2}
              value={comment}
              disabled={locked || busy}
              onChange={(event) => setComment(event.target.value)}
              className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-100"
              placeholder="Required for reject, clarification, and override. Optional for approval."
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button className="btn-primary" disabled={busy || locked} onClick={() => onApprove(comment || undefined)}>
              Approve
            </button>
            <button className="btn-danger" disabled={busy || locked || !comment.trim()} onClick={() => onReject(comment.trim())}>
              Reject
            </button>
            <button className="btn" disabled={busy || locked || !comment.trim()} onClick={() => onClarify(comment.trim())}>
              Request clarification
            </button>
            <button
              className="btn"
              disabled={busy || locked || !canLock}
              onClick={onLock}
              title="Audit lock: Locks an approved row so it cannot be silently changed later."
            >
              Lock
            </button>
          </div>
        </div>

        <details className="rounded-xl border border-slate-200 bg-slate-50 p-3">
          <summary className="cursor-pointer text-sm font-semibold text-slate-800">Override value</summary>
          <div className="mt-3 grid gap-3 md:grid-cols-[220px_1fr_auto] md:items-end">
            <label>
              <span className="text-xs font-semibold uppercase text-slate-500">Field</span>
              <select
                value={field}
                disabled={locked || busy}
                onChange={(event) => setField(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                {overrideFields.map((option) => <option key={option} value={option}>{option.replace(/_/g, " ")}</option>)}
              </select>
              <div className="mt-1 text-xs text-slate-500">
                Current value: {currentValue === null || currentValue === undefined || currentValue === "" ? "Not available" : String(currentValue)}
              </div>
            </label>
            <label>
              <span className="text-xs font-semibold uppercase text-slate-500">New value</span>
              <input
                value={value}
                disabled={locked || busy}
                onChange={(event) => setValue(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="Enter the corrected value"
              />
            </label>
            <button
              className="btn"
              disabled={busy || locked || !comment.trim() || !value.trim()}
              onClick={() => onOverride(field, value.trim(), comment.trim())}
            >
              Save override
            </button>
          </div>
        </details>
      </div>
    </div>
  );
}
