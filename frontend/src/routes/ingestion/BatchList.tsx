import { useEffect, useMemo, useState } from "react";
import { listBatches } from "../../api/client";
import type { IngestionBatch } from "../../api/types";
import BatchTable from "../../components/BatchTable";
import PageHeader from "../../components/PageHeader";
import StatCard from "../../components/StatCard";
import { ErrorState } from "../../components/States";
import { getBatchReviewNeed } from "../../lib/format";

export default function BatchList() {
  const [batches, setBatches] = useState<IngestionBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const params: Record<string, string> = {};
    if (source) params.source = source;
    if (status) params.status = status;
    listBatches(params)
      .then((result) => setBatches(result.results))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [source, status]);

  const summary = useMemo(() => {
    return {
      total: batches.length,
      complete: batches.filter((batch) => batch.status === "COMPLETE").length,
      partial: batches.filter((batch) => batch.status === "PARTIAL").length,
      failed: batches.filter((batch) => batch.status === "FAILED").length,
      rows: batches.reduce((sum, batch) => sum + batch.total_rows, 0),
      review: batches.reduce((sum, batch) => sum + getBatchReviewNeed(batch), 0),
    };
  }, [batches]);

  return (
    <div>
      <PageHeader
        title="What happened after ingestion?"
        description="Each upload or sync becomes a batch. Use this page to see whether ingestion completed, partially completed, or failed."
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <StatCard label="Total batches" value={summary.total} />
        <StatCard label="Completed" value={summary.complete} tone="green" />
        <StatCard label="Partial" value={summary.partial} tone="amber" />
        <StatCard label="Failed" value={summary.failed} tone="red" />
        <StatCard label="Rows processed" value={summary.rows} tone="blue" />
        <StatCard label="Rows needing review" value={summary.review} tone="purple" />
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label>
          <span className="label">Source</span>
          <select
            value={source}
            onChange={(event) => setSource(event.target.value)}
            className="mt-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">All sources</option>
            <option value="sap">SAP</option>
            <option value="utility">Utility</option>
            <option value="travel">Travel</option>
          </select>
        </label>
        <label>
          <span className="label">Status</span>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="mt-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">All statuses</option>
            <option value="COMPLETE">Complete</option>
            <option value="PARTIAL">Partial</option>
            <option value="FAILED">Failed</option>
            <option value="PROCESSING">Processing</option>
          </select>
        </label>
      </div>

      {error ? <ErrorState message={error} /> : <BatchTable batches={batches} loading={loading} />}
    </div>
  );
}
