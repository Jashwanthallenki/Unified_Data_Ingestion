import { useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  mockTravelClearUploads,
  mockTravelSync,
  mockTravelUpload,
  travelSync,
} from "../../api/client";
import type { MockTravelUploadResult } from "../../api/client";
import type { IngestionBatch } from "../../api/types";
import { StatusBadge } from "../../components/Badges";
import PageHeader from "../../components/PageHeader";
import StatCard from "../../components/StatCard";
import { ErrorState } from "../../components/States";
import { batchSourceLabel } from "../../lib/format";

type TravelSegment = {
  segment_type?: string;
  booking_status?: string;
  transport_mode?: string;
};

type TravelTrip = {
  segments?: TravelSegment[];
};

type TravelPreview = {
  total_count: number;
  returned_count: number;
  fixture_trip_count?: number;
  uploaded_trip_count?: number;
  trips: TravelTrip[];
};

export default function TravelSync() {
  const navigate = useNavigate();
  const [startDate, setStartDate] = useState("2025-02-01");
  const [endDate, setEndDate] = useState("2025-05-31");
  const [preview, setPreview] = useState<TravelPreview | null>(null);
  const [batch, setBatch] = useState<IngestionBatch | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<MockTravelUploadResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const categories = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const trip of preview?.trips || []) {
      for (const segment of trip.segments || []) {
        const key = segment.segment_type || segment.transport_mode || "unknown";
        counts[key] = (counts[key] || 0) + 1;
      }
    }
    return counts;
  }, [preview]);

  async function onUploadFile(file: File) {
    setBusy(true);
    setError(null);
    try {
      const result = await mockTravelUpload(file, file.name);
      setUploadResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function onClearUploads() {
    if (!confirm("Clear all uploaded trips? (The bundled fixture stays.)")) return;
    setBusy(true);
    setError(null);
    try {
      const result = await mockTravelClearUploads();
      setUploadResult(null);
      setPreview(null);
      alert(`Cleared ${result.deleted_count} uploaded trip(s).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onPreview() {
    setBusy(true);
    setError(null);
    setPreview(null);
    setBatch(null);
    try {
      const result = await mockTravelSync(startDate, endDate);
      setPreview(result as TravelPreview);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onSync() {
    setBusy(true);
    setError(null);
    setBatch(null);
    try {
      const created = await travelSync(startDate, endDate);
      setBatch(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Guided travel sync"
        description="Optionally upload a Concur/Navan-shaped JSON file into the mock platform, then sync a date range to normalize trips into reviewable ESG activity records."
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <StepCard
            number={1}
            title="Upload travel data (optional)"
            description="Push a Concur/Navan-shaped JSON file into the mock travel platform. Uploaded trips append to the bundled fixture and will appear in the next sync."
            complete={!!uploadResult && uploadResult.accepted_count > 0}
          >
            <div className="flex flex-wrap items-center gap-3">
              <input
                ref={fileInputRef}
                type="file"
                accept="application/json,.json"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) onUploadFile(file);
                }}
                disabled={busy}
                className="block text-sm text-slate-700 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-900 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-slate-700"
              />
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={onClearUploads}
              >
                Clear uploaded trips
              </button>
            </div>
            {uploadResult ? (
              <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
                Accepted {uploadResult.accepted_count} trip(s)
                {uploadResult.rejected_count > 0 ? `, rejected ${uploadResult.rejected_count}` : ""}.
                Total uploaded in mock platform: {uploadResult.total_uploaded_count}.
              </div>
            ) : (
              <p className="mt-3 text-xs text-slate-500">
                Expected shape: <code>{"{ \"trips\": [...] }"}</code> (Concur/Navan-like) or a bare JSON array of trip objects.
                Each trip needs at least <code>trip_id</code> or <code>segments</code>.
              </p>
            )}
          </StepCard>

          <StepCard number={2} title="Select date range" description="Choose the trip window to request from the mock corporate travel API." complete={!!startDate && !!endDate}>
            <div className="grid gap-3 sm:grid-cols-2">
              <label>
                <span className="label">Start date</span>
                <input
                  type="date"
                  value={startDate}
                  onChange={(event) => setStartDate(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </label>
              <label>
                <span className="label">End date</span>
                <input
                  type="date"
                  value={endDate}
                  onChange={(event) => setEndDate(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </label>
            </div>
          </StepCard>

          <StepCard number={3} title="Trigger mock API sync" description="Preview the trips the API would return before creating a batch." complete={!!preview}>
            <button className="btn" disabled={busy || !startDate || !endDate} onClick={onPreview}>
              {busy ? "Requesting preview..." : "Preview API response"}
            </button>
          </StepCard>

          <StepCard number={4} title="Show returned categories" description="Confirm the returned travel categories before normalization." complete={!!preview}>
            {preview ? (
              <div>
                <p className="text-sm text-slate-700">
                  Mock API returned {preview.returned_count} of {preview.total_count} trips for this range
                  {typeof preview.fixture_trip_count === "number" && typeof preview.uploaded_trip_count === "number" ? (
                    <> (<span className="font-medium">{preview.fixture_trip_count}</span> bundled + <span className="font-medium">{preview.uploaded_trip_count}</span> uploaded in the pool)</>
                  ) : null}
                  .
                </p>
                <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  {Object.entries(categories).map(([category, count]) => (
                    <div key={category} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <div className="text-xs font-semibold uppercase text-slate-500">{category}</div>
                      <div className="mt-1 text-xl font-semibold text-slate-950">{count}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-500">Preview the API response to see flights, hotels, cars, rail, and cancelled bookings.</p>
            )}
          </StepCard>

          <StepCard number={5} title="Start normalization" description="Create the ingestion batch and send uncertain rows to analyst review." complete={!!batch}>
            <button className="btn-primary" disabled={busy || !preview} onClick={onSync}>
              {busy ? "Starting normalization..." : "Start normalization"}
            </button>
          </StepCard>

          {error ? <ErrorState message={error} /> : null}
        </div>

        <aside className="space-y-4">
          <div className="card p-5">
            <h2 className="text-base font-semibold text-slate-950">Travel rules applied</h2>
            <ul className="mt-4 space-y-2 text-sm text-slate-700">
              {[
                "Cancelled, refunded, voided, and expense-only rows are excluded.",
                "Flight legs are grouped and checked for codeshare duplicates.",
                "Missing flight distances use airport lookup fallback.",
                "Hotel room-night and same-day stays are normalized for review.",
              ].map((item) => (
                <li key={item} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">{item}</li>
              ))}
            </ul>
          </div>

          {batch ? (
            <div className="card p-5">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-base font-semibold text-slate-950">Batch created</h2>
                <StatusBadge value={batch.status} />
              </div>
              <p className="mt-2 text-sm text-slate-600">{batchSourceLabel(batch)}</p>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <StatCard label="Trips / rows" value={batch.total_rows} />
                <StatCard label="Excluded" value={batch.excluded_rows} tone="gray" />
                <StatCard label="Suspicious" value={batch.suspicious_rows} tone="red" />
                <StatCard label="Low confidence" value={batch.low_confidence_rows} tone="amber" />
              </div>
              <div className="mt-4 flex gap-2">
                <button className="btn-primary" onClick={() => navigate(`/ingestion/batches/${batch.id}`)}>
                  View batch
                </button>
                <Link className="btn" to={`/review/activities?batch=${batch.id}`}>
                  Review records
                </Link>
              </div>
            </div>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

function StepCard({
  number,
  title,
  description,
  complete,
  children,
}: {
  number: number;
  title: string;
  description: string;
  complete?: boolean;
  children: ReactNode;
}) {
  return (
    <section className="card p-5">
      <div className="flex items-start gap-4">
        <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-sm font-bold ${complete ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-700"}`}>
          {number}
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-slate-950">{title}</h2>
          <p className="mt-1 text-sm leading-6 text-slate-600">{description}</p>
          <div className="mt-4">{children}</div>
        </div>
      </div>
    </section>
  );
}
