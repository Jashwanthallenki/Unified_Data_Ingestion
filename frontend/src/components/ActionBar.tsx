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

const duplicateFlags = new Set([
  "DUPLICATE_FILE_UPLOAD",
  "DUPLICATE_ROW_IN_BATCH",
  "CROSS_BATCH_DUPLICATE",
  "DUPLICATE_DOCUMENT",
  "DUPLICATE_SAP_ROW",
  "DUPLICATE_BILL_ACCOUNT_PERIOD",
  "OVERLAPPING_BILLING_PERIOD",
  "POSSIBLE_AMENDED_BILL",
  "DUPLICATE_TRAVEL_EVENT",
  "POSSIBLE_CODESHARE_DUPLICATE",
  "DUPLICATE_FUEL_SOURCE",
  "DOUBLE_COUNT_RISK",
  "REQUIRES_RECONCILIATION",
  "DUPLICATE_TRAVEL_SYNC",
]);

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
  const hasDuplicateRisk = activity.flags.some((flag) => duplicateFlags.has(flag));
  const unresolvedDuplicate = activity.requires_reconciliation || (
    hasDuplicateRisk && !["APPROVED", "MARKED_NOT_RELEVANT", "LOCKED"].includes(activity.review_status)
  );
  const requiresApproveComment = activity.requires_reconciliation;
  const canLock = activity.review_status === "APPROVED" && !locked && !unresolvedDuplicate;
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
              placeholder="Required for reject, clarification, override, and unresolved duplicate reconciliation. Optional for normal approval."
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              className="btn-primary"
              disabled={busy || locked || (requiresApproveComment && !comment.trim())}
              onClick={() => onApprove(comment || undefined)}
              title={requiresApproveComment ? "Duplicate or reconciliation-risk rows require an analyst comment before approval." : undefined}
            >
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
              title={unresolvedDuplicate ? "Resolve duplicate/reconciliation context before audit lock." : "Audit lock: Locks an approved row so it cannot be silently changed later."}
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
