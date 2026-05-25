import { Link } from "react-router-dom";
import type { IngestionBatch } from "../api/types";
import { SourceBadge, StatusBadge } from "./Badges";
import { EmptyState, LoadingState } from "./States";
import { batchSourceLabel, formatDateTime, shortId } from "../lib/format";

export default function BatchTable({ batches, loading }: { batches: IngestionBatch[]; loading: boolean }) {
  if (loading) return <LoadingState label="Loading ingestion batches..." />;
  if (!batches.length) {
    return (
      <EmptyState
        title="Start by uploading SAP, utility, or syncing travel data."
        message="Every ingestion creates a batch, and every batch explains what succeeded, failed, or was intentionally excluded."
        action={<Link to="/ingestion" className="btn-primary">Choose a source</Link>}
      />
    );
  }

  return (
    <div className="card overflow-x-auto">
      <table className="table-default min-w-full">
        <thead>
          <tr>
            <th>Batch ID</th>
            <th>Source</th>
            <th>Method</th>
            <th>Uploaded / synced at</th>
            <th>Status</th>
            <th>Total rows</th>
            <th>Eligible</th>
            <th>Excluded</th>
            <th>Failed</th>
            <th>Low confidence</th>
            <th>AI suggested</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {batches.map((batch) => (
            <tr key={batch.id}>
              <td>
                <div className="font-mono text-xs text-slate-700">{shortId(batch.id)}</div>
                <div className="max-w-44 truncate text-xs text-slate-500">{batchSourceLabel(batch)}</div>
              </td>
              <td><SourceBadge value={batch.source_type} /></td>
              <td>{batch.ingestion_method === "API_PULL" ? "API sync" : "File upload"}</td>
              <td>{formatDateTime(batch.uploaded_at)}</td>
              <td><StatusBadge value={batch.status} /></td>
              <td>{batch.total_rows}</td>
              <td>{batch.eligible_rows}</td>
              <td>{batch.excluded_rows}</td>
              <td>{batch.failed_rows}</td>
              <td>{batch.low_confidence_rows}</td>
              <td>{batch.llm_suggested_rows}</td>
              <td>
                <Link to={`/ingestion/batches/${batch.id}`} className="btn py-1 text-xs">
                  View batch
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
