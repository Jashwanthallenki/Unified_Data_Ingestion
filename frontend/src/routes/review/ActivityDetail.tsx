import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  acceptLlm,
  approveActivity,
  getActivity,
  groqSuggest,
  ignoreDuplicate,
  lockActivity,
  markDuplicate,
  markNotDuplicate,
  overrideActivity,
  rejectActivity,
  rejectLlm,
  requestClarification,
  useAsSourceOfTruth,
} from "../../api/client";
import type { GroqSuggestResponse, NormalizedActivityDetail } from "../../api/types";
import ActionBar from "../../components/ActionBar";
import ActivityDetailPanel from "../../components/ActivityDetailPanel";
import FieldProvenanceTable from "../../components/FieldProvenanceTable";
import GroqSuggestionCard from "../../components/GroqSuggestionCard";
import PageHeader from "../../components/PageHeader";
import RawVsNormalizedView from "../../components/RawVsNormalizedView";
import ReviewTimeline from "../../components/ReviewTimeline";
import { ErrorState, LoadingState } from "../../components/States";
import ValidationIssueList from "../../components/ValidationIssueList";

export default function ActivityDetail() {
  const { id } = useParams<{ id: string }>();
  const [activity, setActivity] = useState<NormalizedActivityDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [groqResult, setGroqResult] = useState<GroqSuggestResponse | null>(null);
  const [duplicateComment, setDuplicateComment] = useState("");

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function refresh() {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      setActivity(await getActivity(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function runAction(fn: () => Promise<NormalizedActivityDetail>) {
    setBusy(true);
    setError(null);
    try {
      setActivity(await fn());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function requestGroqSuggestion() {
    if (!activity) return;
    setBusy(true);
    setError(null);
    setGroqResult(null);
    try {
      const result = await groqSuggest(activity.id);
      setGroqResult(result);
      if (result.ok) {
        setActivity(await getActivity(activity.id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const fieldValues = useMemo(() => {
    return activity ? (activity as unknown as Record<string, unknown>) : {};
  }, [activity]);

  if (loading) return <LoadingState label="Loading activity record..." />;
  if (error && !activity) return <ErrorState message={error} />;
  if (!activity) return <ErrorState title="Activity record not found" message="The record may have been removed or the URL is incomplete." />;

  const locked = !!activity.locked_at || activity.review_status === "LOCKED";

  return (
    <div className="pb-40">
      <PageHeader
        title="Activity record"
        description="Review the source row, normalized values, validation issues, provenance, and available actions."
        actions={
          <>
            <Link to="/review/activities" className="btn">Back to queue</Link>
            <Link to={`/review/activities?batch=${activity.batch}`} className="btn">Batch records</Link>
          </>
        }
      />

      {error ? <div className="mb-4"><ErrorState message={error} /></div> : null}

      <div className="space-y-6">
        <ActivityDetailPanel activity={activity} />

        {(activity.is_duplicate || activity.requires_reconciliation || activity.duplicate_of_activity || activity.flags.some((flag) => flag.includes("DUPLICATE") || flag === "DOUBLE_COUNT_RISK")) ? (
          <section className="rounded-xl border border-amber-200 bg-amber-50 p-5 shadow-sm">
            <h2 className="text-base font-semibold text-amber-950">Duplicate / Reconciliation Context</h2>
            <p className="mt-2 text-sm leading-6 text-amber-900">
              This record may duplicate another source row. It was preserved for audit, but it should not be counted twice unless an analyst confirms it represents a separate activity.
            </p>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <Info label="Current event key" value={activity.event_key || "Not available"} />
              <Info label="Duplicate of activity" value={activity.duplicate_of_activity || "Not linked"} />
              <Info label="Duplicate reason" value={activity.duplicate_reason || "Detected by source hash or event key"} />
              <Info label="Source hierarchy recommendation" value={activity.source_hierarchy_rank ? `Rank ${activity.source_hierarchy_rank}: ${activity.source_of_truth || "source"}` : "Needs analyst judgment"} />
            </div>
            {!locked ? (
              <div className="mt-4">
                <label>
                  <span className="label">Reconciliation comment</span>
                  <textarea
                    rows={2}
                    value={duplicateComment}
                    onChange={(event) => setDuplicateComment(event.target.value)}
                    className="mt-1 w-full rounded-xl border border-amber-300 bg-white px-3 py-2 text-sm"
                    placeholder="Required for duplicate reconciliation actions."
                  />
                </label>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button className="btn" disabled={busy || !duplicateComment.trim()} onClick={() => runAction(() => markDuplicate(activity.id, duplicateComment.trim()))}>Mark as duplicate</button>
                  <button className="btn" disabled={busy || !duplicateComment.trim()} onClick={() => runAction(() => markNotDuplicate(activity.id, duplicateComment.trim()))}>Mark as not duplicate</button>
                  <button className="btn-primary" disabled={busy || !duplicateComment.trim()} onClick={() => runAction(() => useAsSourceOfTruth(activity.id, duplicateComment.trim()))}>Use this record</button>
                  <button className="btn" disabled={busy || !duplicateComment.trim()} onClick={() => runAction(() => ignoreDuplicate(activity.id, duplicateComment.trim()))}>Ignore this duplicate</button>
                </div>
              </div>
            ) : null}
          </section>
        ) : null}

        <RawVsNormalizedView activity={activity} />

        <section className="card p-5">
          <h2 className="text-base font-semibold text-slate-950">Validation Issues</h2>
          <p className="mt-1 text-sm text-slate-600">Each issue explains why this record may need analyst attention before approval.</p>
          <div className="mt-4">
            <ValidationIssueList issues={activity.issues} />
          </div>
        </section>

        <FieldProvenanceTable provenance={activity.field_provenance || {}} values={fieldValues} />

        <section className="card p-5">
          <h2 className="text-base font-semibold text-slate-950">Groq Suggestions</h2>
          <p className="mt-1 text-sm text-slate-600">
            AI suggestions are advisory. They do not become final activity values until accepted by an analyst.
          </p>
          <div className="mt-4">
            <GroqSuggestionCard
              suggestions={activity.llm_suggestions || []}
              result={groqResult}
              busy={busy}
              locked={locked}
              onRequest={requestGroqSuggestion}
              onAccept={(field) => runAction(() => acceptLlm(activity.id, field))}
              onReject={(field) => runAction(() => rejectLlm(activity.id, field))}
            />
          </div>
        </section>

        <section className="card p-5">
          <h2 className="text-base font-semibold text-slate-950">Review History</h2>
          <p className="mt-1 text-sm text-slate-600">A timeline of ingestion, flags, AI decisions, analyst actions, approval, and audit lock.</p>
          <div className="mt-4">
            <ReviewTimeline logs={activity.review_logs} createdAt={activity.created_at} flags={activity.flags} />
          </div>
        </section>

        {locked && activity.locked_snapshot ? (
          <section className="card p-5">
            <h2 className="text-base font-semibold text-slate-950">Audit lock snapshot</h2>
            <p className="mt-1 text-sm text-slate-600">
              Audit lock: Locks an approved row so it cannot be silently changed later.
            </p>
            <pre className="mt-4 max-h-80 overflow-auto rounded-xl bg-slate-50 p-4 text-xs text-slate-700">
              {JSON.stringify(activity.locked_snapshot, null, 2)}
            </pre>
          </section>
        ) : null}
      </div>

      <ActionBar
        activity={activity}
        busy={busy}
        onApprove={(comment) => runAction(() => approveActivity(activity.id, comment))}
        onReject={(comment) => runAction(() => rejectActivity(activity.id, comment))}
        onClarify={(comment) => runAction(() => requestClarification(activity.id, comment))}
        onOverride={(field, value, comment) => runAction(() => overrideActivity(activity.id, field, value, comment))}
        onLock={() => runAction(() => lockActivity(activity.id))}
      />
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-white/70 p-3">
      <div className="text-xs font-semibold uppercase text-amber-700">{label}</div>
      <div className="mt-1 break-all text-sm font-medium text-slate-900">{value}</div>
    </div>
  );
}
