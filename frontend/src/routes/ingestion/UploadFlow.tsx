import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { uploadSap, uploadUtility } from "../../api/client";
import type { IngestionBatch } from "../../api/types";
import { StatusBadge } from "../../components/Badges";
import PageHeader from "../../components/PageHeader";
import StatCard from "../../components/StatCard";
import { ErrorState } from "../../components/States";
import { batchSourceLabel, humanize } from "../../lib/format";

type UploadSource = "sap" | "utility";

const sapMovementLogic = [
  ["261", "Fuel consumption", "Creates activity record"],
  ["262", "Reversal", "Creates reversal record and flag"],
  ["101", "Receipt", "Excluded to avoid purchase/consumption double count"],
  ["301 / 311", "Transfer", "Excluded because stock moved internally"],
  ["551", "Scrap", "Needs review"],
];

const utilityBillingLogic = [
  "Meter number and account are used for facility matching.",
  "Billing start/end dates are used to pro-rate usage across calendar months.",
  "Estimated readings are kept but capped at medium confidence.",
  "Tax-only, late-fee-only, amount-only, refund, and gas rows are excluded.",
];

function readHeaderLine(text: string) {
  const firstLine = text.split(/\r?\n/)[0] || "";
  const commaCount = (firstLine.match(/,/g) || []).length;
  const semicolonCount = (firstLine.match(/;/g) || []).length;
  const delimiter = semicolonCount > commaCount ? ";" : ",";
  return firstLine.split(delimiter).map((part) => part.trim().replace(/^"|"$/g, "")).filter(Boolean);
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
  children?: ReactNode;
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
          {children ? <div className="mt-4">{children}</div> : null}
        </div>
      </div>
    </section>
  );
}

export default function UploadFlow({ defaultSource = "sap" }: { defaultSource?: UploadSource }) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const querySource = searchParams.get("source");
  const source: UploadSource = querySource === "utility" || querySource === "sap" ? querySource : defaultSource;
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<"mb51" | "me2m">("mb51");
  const [columns, setColumns] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [batch, setBatch] = useState<IngestionBatch | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setFile(null);
    setColumns([]);
    setBatch(null);
    setError(null);
  }, [source]);

  const detected = useMemo(() => {
    const lower = columns.map((column) => column.toLowerCase());
    if (source === "sap") {
      return {
        primary: lower.filter((column) => ["werk", "plant", "materialnummer", "material", "menge", "quantity", "me", "unit", "bewegungsart", "movement type"].includes(column)),
        missingHint: "Expected plant, material, quantity, unit, movement type, and document fields.",
      };
    }
    return {
      primary: lower.filter((column) => column.includes("meter") || column.includes("billing") || column.includes("usage") || column.includes("reading")),
      missingHint: "Expected meter, billing start/end, usage, reading type, amount, and service fields.",
    };
  }, [columns, source]);

  function setSource(next: UploadSource) {
    const params = new URLSearchParams(searchParams);
    params.set("source", next);
    setSearchParams(params);
  }

  async function onFileChange(nextFile: File | null) {
    setFile(nextFile);
    setBatch(null);
    setError(null);
    if (!nextFile) {
      setColumns([]);
      return;
    }
    const text = await nextFile.text();
    setColumns(readHeaderLine(text));
  }

  async function onSubmit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setBatch(null);
    try {
      const created = source === "sap" ? await uploadSap(file, kind) : await uploadUtility(file);
      setBatch(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const isSap = source === "sap";

  return (
    <div>
      <PageHeader
        title={isSap ? "Guided SAP upload" : "Guided utility upload"}
        description={
          isSap
            ? "Bring in SAP fuel or procurement data with column preview, lookup checks, and movement-type logic before ingestion starts."
            : "Bring in utility electricity data with meter, billing-period, and estimated-reading checks before ingestion starts."
        }
        actions={
          <>
            <button className={source === "sap" ? "btn-primary" : "btn"} onClick={() => setSource("sap")}>SAP</button>
            <button className={source === "utility" ? "btn-primary" : "btn"} onClick={() => setSource("utility")}>Utility</button>
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <StepCard
            number={1}
            title={isSap ? "Upload SAP file" : "Upload utility CSV"}
            description={isSap ? "Select an MB51 or ME2M CSV export." : "Select the electricity export from the utility portal."}
            complete={!!file}
          >
            {isSap ? (
              <label className="mb-4 block max-w-sm">
                <span className="label">SAP file kind</span>
                <select
                  value={kind}
                  onChange={(event) => setKind(event.target.value as "mb51" | "me2m")}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                >
                  <option value="mb51">MB51 - goods movements</option>
                  <option value="me2m">ME2M - procurement</option>
                </select>
              </label>
            ) : null}
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => onFileChange(event.target.files?.[0] || null)}
              className="block w-full rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-sm text-slate-600"
            />
            <p className="mt-3 text-xs text-slate-500">
              Sample file: {isSap ? "backend/fixtures/sap/sap_mb51_fuel_movements.csv or sap_me2m_procurement.csv" : "backend/fixtures/utility/utility_electricity_export.csv"}.
            </p>
          </StepCard>

          {isSap ? (
            <StepCard
              number={2}
              title="Confirm lookup files"
              description="The prototype uses loaded lookup tables for plant, material, units, cost center, and movement types."
              complete
            >
              <div className="grid gap-2 sm:grid-cols-2">
                {["Plant lookup", "Material lookup", "Unit mapping", "Movement-type mapping"].map((item) => (
                  <div key={item} className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-800">
                    {item} loaded
                  </div>
                ))}
              </div>
            </StepCard>
          ) : null}

          <StepCard
            number={isSap ? 3 : 2}
            title={isSap ? "Preview detected columns" : "Preview detected meter fields"}
            description={columns.length ? "These are the columns the browser detected before sending the file to Django." : "Choose a file to preview detected columns."}
            complete={columns.length > 0}
          >
            {columns.length ? (
              <div className="flex flex-wrap gap-2">
                {columns.map((column) => (
                  <span key={column} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700">
                    {column}
                  </span>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">{detected.missingHint}</div>
            )}
          </StepCard>

          <StepCard
            number={isSap ? 4 : 3}
            title={isSap ? "Preview movement-type logic" : "Preview billing period fields"}
            description={isSap ? "These rules decide whether SAP rows become activity records or intentional exclusions." : "These rules decide how bills become monthly electricity activity records."}
            complete={columns.length > 0}
          >
            {isSap ? (
              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="min-w-full text-sm">
                  <tbody>
                    {sapMovementLogic.map(([code, label, outcome]) => (
                      <tr key={code} className="border-b border-slate-100 last:border-b-0">
                        <td className="px-3 py-2 font-mono text-xs text-slate-600">{code}</td>
                        <td className="px-3 py-2 font-medium text-slate-900">{label}</td>
                        <td className="px-3 py-2 text-slate-600">{outcome}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <ul className="space-y-2">
                {utilityBillingLogic.map((item) => (
                  <li key={item} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{item}</li>
                ))}
              </ul>
            )}
          </StepCard>

          <StepCard
            number={isSap ? 5 : 4}
            title="Start ingestion"
            description="The backend will store raw rows, create activity records, and send uncertain rows to the review queue."
            complete={!!batch}
          >
            <button className="btn-primary" disabled={!file || busy} onClick={onSubmit}>
              {busy ? "Starting ingestion..." : "Start ingestion"}
            </button>
          </StepCard>

          {error ? <ErrorState message={error} /> : null}
        </div>

        <aside className="space-y-4">
          <div className="card p-5">
            <h2 className="text-base font-semibold text-slate-950">Pre-ingestion checklist</h2>
            <div className="mt-4 space-y-3">
              <ChecklistItem label="Source file selected" complete={!!file} />
              <ChecklistItem label="Columns previewed" complete={columns.length > 0} />
              <ChecklistItem label={isSap ? "Lookup tables available" : "Meter and billing fields reviewed"} complete />
              <ChecklistItem label={isSap ? "Movement logic reviewed" : "Billing logic reviewed"} complete={columns.length > 0} />
            </div>
          </div>

          {detected.primary.length ? (
            <div className="card p-5">
              <h2 className="text-base font-semibold text-slate-950">Detected signal</h2>
              <p className="mt-2 text-sm text-slate-600">
                {humanize(source)} file contains {detected.primary.length} expected field signals.
              </p>
            </div>
          ) : null}

          {batch ? (
            <div className="card p-5">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-base font-semibold text-slate-950">Batch created</h2>
                <StatusBadge value={batch.status} />
              </div>
              <p className="mt-2 text-sm text-slate-600">{batchSourceLabel(batch)}</p>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <StatCard label="Total rows" value={batch.total_rows} />
                <StatCard label="Excluded" value={batch.excluded_rows} tone="gray" />
                <StatCard label="Low confidence" value={batch.low_confidence_rows} tone="amber" />
                <StatCard label="AI suggested" value={batch.llm_suggested_rows} tone="purple" />
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

function ChecklistItem({ label, complete }: { label: string; complete: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <span className={complete ? "text-emerald-700" : "text-slate-400"}>{complete ? "Ready" : "Waiting"}</span>
    </div>
  );
}
