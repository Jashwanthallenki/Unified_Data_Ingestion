import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getBatch, getBatchDuplicates, listActivities, listBatchExclusions, listBatchRaw } from "../../api/client";
import type { BatchDuplicateInfo, ExclusionRow, IngestionBatch, NormalizedActivity, RawRecord } from "../../api/types";
import ActivityTable from "../../components/ActivityTable";
import { SourceBadge, StatusBadge } from "../../components/Badges";
import PageHeader from "../../components/PageHeader";
import StatCard from "../../components/StatCard";
import { EmptyState, ErrorState, LoadingState } from "../../components/States";
import {
  batchSourceLabel,
  formatDateTime,
  friendlyExclusion,
  friendlyEligibility,
  shortId,
} from "../../lib/format";

const tabs = ["Summary", "Normalized Rows", "Excluded Rows", "Failed Rows", "Validation Issues", "Duplicates"] as const;
type Tab = (typeof tabs)[number];

export default function BatchDetail() {
  const { id } = useParams<{ id: string }>();
  const [batch, setBatch] = useState<IngestionBatch | null>(null);
  const [activities, setActivities] = useState<NormalizedActivity[]>([]);
  const [rawRows, setRawRows] = useState<RawRecord[]>([]);
  const [exclusions, setExclusions] = useState<ExclusionRow[]>([]);
  const [duplicates, setDuplicates] = useState<BatchDuplicateInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("Summary");

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    Promise.all([
      getBatch(id),
      listActivities({ batch: id }),
      listBatchRaw(id),
      listBatchExclusions(id),
      getBatchDuplicates(id),
    ])
      .then(([batchResult, activityResult, rawResult, exclusionResult, duplicateResult]) => {
        setBatch(batchResult);
        setActivities(activityResult.results);
        setRawRows(rawResult.results);
        setExclusions(exclusionResult.results);
        setDuplicates(duplicateResult);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [id]);

  const failedRows = useMemo(() => rawRows.filter((row) => row.parse_status === "FAILED" || row.error_message), [rawRows]);
  const issueRows = useMemo(() => activities.filter((activity) => activity.issue_count > 0), [activities]);

  if (loading) return <LoadingState label="Loading batch details..." />;
  if (error) return <ErrorState message={error} />;
  if (!batch) {
    return <EmptyState title="Batch not found" message="The batch may have been removed or the URL is incomplete." />;
  }

  return (
    <div>
      <PageHeader
        title="Which rows succeeded, failed, or were excluded?"
        description="Batch details connect the original ingestion event to normalized activity records and review outcomes."
        actions={
          <>
            <Link to="/ingestion/batches" className="btn">All batches</Link>
            <Link to={`/review/activities?batch=${batch.id}`} className="btn-primary">Open review records</Link>
          </>
        }
      />

      <section className="card mb-6 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <SourceBadge value={batch.source_type} />
              <StatusBadge value={batch.status} />
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700">
                Batch {shortId(batch.id)}
              </span>
            </div>
            <h2 className="mt-4 text-lg font-semibold text-slate-950">{batchSourceLabel(batch)}</h2>
            <p className="mt-1 text-sm text-slate-600">
              {batch.ingestion_method === "API_PULL" ? "API sync" : "File upload"} at {formatDateTime(batch.uploaded_at)}
            </p>
            {batch.notes ? <p className="mt-2 text-sm text-slate-600">{batch.notes}</p> : null}
          </div>
          {batch.error_message ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
              {batch.error_message}
            </div>
          ) : null}
        </div>
      </section>

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-7">
        <StatCard label="Total rows" value={batch.total_rows} />
        <StatCard label="Successful rows" value={batch.successful_rows} tone="green" />
        <StatCard label="Excluded rows" value={batch.excluded_rows} tone="gray" />
        <StatCard label="Failed rows" value={batch.failed_rows} tone="red" />
        <StatCard label="Suspicious rows" value={batch.suspicious_rows} tone="red" />
        <StatCard label="Low confidence" value={batch.low_confidence_rows} tone="amber" />
        <StatCard label="AI suggested" value={batch.llm_suggested_rows} tone="purple" />
      </div>

      <div className="mb-4 flex gap-2 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab}
            className={activeTab === tab ? "btn-primary shrink-0" : "btn shrink-0"}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "Summary" ? <SummaryTab batch={batch} /> : null}
      {activeTab === "Normalized Rows" ? <ActivityTable activities={activities} loading={false} emptyMessage="No normalized rows were created for this batch." /> : null}
      {activeTab === "Excluded Rows" ? <ExcludedTab exclusions={exclusions} /> : null}
      {activeTab === "Failed Rows" ? <FailedTab rows={failedRows} /> : null}
      {activeTab === "Validation Issues" ? <ValidationTab activities={issueRows} /> : null}
      {activeTab === "Duplicates" ? <DuplicatesTab duplicates={duplicates} /> : null}
    </div>
  );
}

function SummaryTab({ batch }: { batch: IngestionBatch }) {
  const versions = [
    ["Plant lookup", batch.plant_lookup_version],
    ["Material lookup", batch.material_lookup_version],
    ["Unit mapping", batch.unit_mapping_version],
    ["Meter mapping", batch.meter_mapping_version],
    ["Emission factors", batch.ef_version],
  ];

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-950">What happened in this batch?</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          The ingestion adapter parsed source rows, intentionally excluded rows that should not become emissions
          activity, and created normalized records for analyst review.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <StatCard label="Pending review" value={batch.pending_rows} tone="amber" />
          <StatCard label="Approved" value={batch.approved_rows} tone="green" />
          <StatCard label="Rejected" value={batch.rejected_rows} tone="red" />
          <StatCard label="Locked" value={batch.locked_rows} tone="green" />
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-slate-950">Lookup versions used</h2>
        <p className="mt-2 text-sm text-slate-600">These versions explain what reference data shaped the normalization.</p>
        <dl className="mt-4 divide-y divide-slate-100">
          {versions.map(([label, value]) => (
            <div key={label} className="grid grid-cols-2 gap-3 py-2">
              <dt className="text-sm font-medium text-slate-600">{label}</dt>
              <dd className="text-sm text-slate-900">{value || "Not used for this source"}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}

function ExcludedTab({ exclusions }: { exclusions: ExclusionRow[] }) {
  if (!exclusions.length) {
    return <EmptyState title="No rows were excluded in this batch." message="Every parsed source row either became an activity record or is visible in another tab." />;
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
        These rows were not lost. They were intentionally excluded because the source row did not represent ESG activity
        or would create double counting.
      </div>
      <div className="card overflow-x-auto">
        <table className="table-default min-w-full">
          <thead>
            <tr>
              <th>Row</th>
              <th>Reason</th>
              <th>ESG relevance</th>
              <th>Original source row excerpt</th>
            </tr>
          </thead>
          <tbody>
            {exclusions.map((row) => (
              <tr key={row.id}>
                <td>{row.row_number}</td>
                <td>
                  <div className="font-medium text-slate-900">{friendlyExclusion(row.exclusion_reason)}</div>
                  <div className="font-mono text-xs text-slate-500">{row.exclusion_reason}</div>
                </td>
                <td>{friendlyEligibility(row.eligibility_status)}</td>
                <td className="max-w-xl truncate text-xs text-slate-500">{JSON.stringify(row.raw_payload)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FailedTab({ rows }: { rows: RawRecord[] }) {
  if (!rows.length) {
    return <EmptyState title="No failed rows in this batch." message="Parsing and normalization did not produce row-level failures." />;
  }

  return (
    <div className="card overflow-x-auto">
      <table className="table-default min-w-full">
        <thead>
          <tr>
            <th>Row</th>
            <th>Status</th>
            <th>Error</th>
            <th>Original source row excerpt</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.row_number}</td>
              <td>{row.parse_status}</td>
              <td>{row.error_message || "No error message recorded"}</td>
              <td className="max-w-xl truncate text-xs text-slate-500">{JSON.stringify(row.raw_payload)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ValidationTab({ activities }: { activities: NormalizedActivity[] }) {
  if (!activities.length) {
    return <EmptyState title="No validation issues in this batch." message="No normalized rows in this batch currently have validation issues." />;
  }

  return (
    <div className="card overflow-x-auto">
      <table className="table-default min-w-full">
        <thead>
          <tr>
            <th>Activity</th>
            <th>Location</th>
            <th>Issue count</th>
            <th>Confidence</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {activities.map((activity) => (
            <tr key={activity.id}>
              <td>
                <div className="font-medium text-slate-900">{activity.activity_type}</div>
                <div className="text-xs text-slate-500">{activity.activity_subtype || "Subtype not set"}</div>
              </td>
              <td>{activity.facility_name || activity.origin || activity.vendor || "Not available"}</td>
              <td>{activity.issue_count}</td>
              <td>{activity.confidence_level}</td>
              <td><Link className="btn py-1 text-xs" to={`/review/activities/${activity.id}`}>Inspect issues</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DuplicatesTab({ duplicates }: { duplicates: BatchDuplicateInfo | null }) {
  const rawRows = duplicates?.duplicate_raw_rows || [];
  const activities = duplicates?.duplicate_activities || [];
  if (!rawRows.length && !activities.length) {
    return (
      <EmptyState
        title="No duplicates detected in this batch."
        message="If this batch duplicates another upload or sync, duplicate raw rows and activities will appear here."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        Duplicate rows are preserved for audit. They are flagged so an analyst can prevent double counting before lock.
      </div>
      {rawRows.length ? (
        <section className="card overflow-x-auto">
          <div className="border-b border-slate-200 p-4">
            <h2 className="text-base font-semibold text-slate-950">Duplicate raw rows</h2>
          </div>
          <table className="table-default min-w-full">
            <thead>
              <tr>
                <th>Row</th>
                <th>Source event key</th>
                <th>Duplicate of raw row</th>
                <th>Raw excerpt</th>
              </tr>
            </thead>
            <tbody>
              {rawRows.map((row) => (
                <tr key={row.id}>
                  <td>{row.row_number}</td>
                  <td className="max-w-md truncate font-mono text-xs">{row.source_event_key || row.row_hash}</td>
                  <td className="font-mono text-xs">{row.duplicate_of_raw_record ? shortId(row.duplicate_of_raw_record) : "In batch"}</td>
                  <td className="max-w-xl truncate text-xs text-slate-500">{JSON.stringify(row.raw_payload)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
      {activities.length ? (
        <section>
          <h2 className="mb-2 text-base font-semibold text-slate-950">Duplicate activities</h2>
          <ActivityTable activities={activities} loading={false} emptyMessage="No duplicate activities." />
        </section>
      ) : null}
    </div>
  );
}
