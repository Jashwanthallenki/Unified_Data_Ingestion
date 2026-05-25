import { Link } from "react-router-dom";
import PageHeader from "../../components/PageHeader";

const sources = [
  {
    icon: "SAP",
    title: "SAP Fuel / Procurement",
    accepts: "MB51 / ME2M CSV exports",
    issues: ["Plant, material, and unit lookup coverage", "Movement-type filtering", "Transfers and reversals"],
    cta: "Upload SAP File",
    to: "/ingestion/upload?source=sap",
  },
  {
    icon: "kWh",
    title: "Utility Electricity",
    accepts: "Utility electricity CSV exports",
    issues: ["Billing periods", "Estimated readings", "Meter to facility matching"],
    cta: "Upload Utility File",
    to: "/ingestion/upload?source=utility",
  },
  {
    icon: "TRV",
    title: "Corporate Travel",
    accepts: "Mocked Concur/Navan API sync",
    issues: ["Flights, hotels, car, and rail", "Cancelled bookings", "Codeshares and missing distances"],
    cta: "Sync Travel Data",
    to: "/ingestion/travel-sync",
  },
];

export default function SourceSelection() {
  return (
    <div>
      <PageHeader
        title="What data do I want to bring in?"
        description="Choose a source. Each ingestion creates a batch, preserves the original source rows, and sends uncertain activity records to analyst review."
      />

      <div className="grid gap-5 xl:grid-cols-3">
        {sources.map((source) => (
          <article key={source.title} className="card flex flex-col p-6">
            <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-xl border border-slate-200 bg-slate-50 text-sm font-bold text-slate-800">
              {source.icon}
            </div>
            <h2 className="text-lg font-semibold text-slate-950">{source.title}</h2>
            <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-xs font-semibold uppercase text-slate-500">What it accepts</div>
              <div className="mt-1 text-sm font-medium text-slate-900">{source.accepts}</div>
            </div>
            <div className="mt-4 flex-1">
              <div className="text-xs font-semibold uppercase text-slate-500">Common issues detected</div>
              <ul className="mt-2 space-y-2">
                {source.issues.map((issue) => (
                  <li key={issue} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
                    {issue}
                  </li>
                ))}
              </ul>
            </div>
            <Link to={source.to} className="btn-primary mt-6 w-full">
              {source.cta}
            </Link>
          </article>
        ))}
      </div>
    </div>
  );
}
