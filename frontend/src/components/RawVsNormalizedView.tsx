import type { NormalizedActivityDetail } from "../api/types";
import type { ReactNode } from "react";
import {
  formatActivityDate,
  formatActivityLocation,
  formatNumber,
  formatQuantity,
  friendlyEligibility,
  friendlyMethod,
} from "../lib/format";

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid grid-cols-5 gap-3 border-b border-slate-100 py-2 last:border-b-0">
      <dt className="col-span-2 text-xs font-semibold uppercase text-slate-500">{label}</dt>
      <dd className="col-span-3 text-sm text-slate-800">{value}</dd>
    </div>
  );
}

function formatRawValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "Not available";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function RawVsNormalizedView({ activity }: { activity: NormalizedActivityDetail }) {
  const rawEntries = Object.entries(activity.raw_payload || {}).slice(0, 18);

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <section className="card p-5">
        <div className="mb-4">
          <h2 className="text-base font-semibold text-slate-950">Original Source Row</h2>
          <p className="mt-1 text-sm text-slate-600">The row as it arrived from SAP, utility export, or travel sync.</p>
        </div>
        {rawEntries.length ? (
          <dl>
            {rawEntries.map(([key, value]) => (
              <Row key={key} label={key} value={formatRawValue(value)} />
            ))}
          </dl>
        ) : (
          <p className="text-sm text-slate-500">No raw source row is attached to this record.</p>
        )}
      </section>

      <section className="card p-5">
        <div className="mb-4">
          <h2 className="text-base font-semibold text-slate-950">Activity Record</h2>
          <p className="mt-1 text-sm text-slate-600">The normalized ESG record created from the source row.</p>
        </div>
        <dl>
          <Row label="Activity type" value={activity.activity_type} />
          <Row label="Subtype" value={activity.activity_subtype || "Not available"} />
          <Row label="Facility" value={formatActivityLocation(activity)} />
          <Row label="Date / period" value={formatActivityDate(activity)} />
          <Row label="Quantity" value={formatQuantity(activity)} />
          <Row label="Scope" value={activity.scope ? `Scope ${activity.scope} ${activity.scope_category || ""}` : "Not available"} />
          <Row label="ESG relevance" value={friendlyEligibility(activity.eligibility_status)} />
          <Row label="Calculation" value={friendlyMethod(activity.calculation_method)} />
          <Row label="Emission method" value={friendlyMethod(activity.emission_method)} />
          <Row label="Emission factor" value={activity.emission_factor ? `${activity.emission_factor} (${activity.emission_factor_source || "source unknown"})` : "Not available"} />
          <Row label="CO2e" value={activity.co2e_kg ? `${formatNumber(activity.co2e_kg, 2)} kg` : "Not available"} />
          <Row label="Reference" value={activity.reference_id || "Not available"} />
        </dl>
      </section>
    </div>
  );
}
