import { MethodBadge } from "./Badges";
import { friendlyMethod, formatNumber, humanize } from "../lib/format";

type Provenance = Record<
  string,
  {
    method: string;
    rule?: string;
    confidence?: number;
    reason?: string;
    source_field?: string;
    note?: string;
  }
>;

export default function FieldProvenanceTable({
  provenance,
  values,
}: {
  provenance: Provenance;
  values: Record<string, unknown>;
}) {
  const entries = Object.entries(provenance || {});

  if (!entries.length) {
    return (
      <div className="card p-5">
        <h2 className="text-base font-semibold text-slate-950">How this value was derived</h2>
        <p className="mt-2 text-sm text-slate-600">No field-level provenance was recorded for this activity.</p>
      </div>
    );
  }

  return (
    <div className="card overflow-x-auto">
      <div className="border-b border-slate-200 p-5">
        <h2 className="text-base font-semibold text-slate-950">How this value was derived</h2>
        <p className="mt-1 text-sm text-slate-600">
          Shows whether each value came directly from the source, rules, AI suggestion, or analyst override.
        </p>
      </div>
      <table className="table-default min-w-full">
        <thead>
          <tr>
            <th>Field</th>
            <th>Value</th>
            <th>Method</th>
            <th>Source / rule</th>
            <th>Confidence</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([field, item]) => (
            <tr key={field}>
              <td className="font-medium text-slate-900">{humanize(field)}</td>
              <td>{formatValue(values[field])}</td>
              <td><MethodBadge value={item.method} /></td>
              <td>
                <div className="max-w-md text-sm text-slate-700">
                  {item.rule || item.source_field || item.reason || item.note || friendlyMethod(item.method)}
                </div>
              </td>
              <td>{item.confidence !== undefined ? formatNumber(item.confidence * 100, 0) + "%" : "Not available"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "Not available";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
