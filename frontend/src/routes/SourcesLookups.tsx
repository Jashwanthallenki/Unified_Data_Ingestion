import PageHeader from "../components/PageHeader";

const sources = [
  {
    title: "SAP Fuel / Procurement",
    rows: ["Plant lookup", "Material lookup", "Unit mapping", "Movement-type mapping", "Cost center lookup"],
  },
  {
    title: "Utility Electricity",
    rows: ["Meter to facility lookup", "Electricity export schema", "Billing period fields", "Estimated reading marker"],
  },
  {
    title: "Corporate Travel",
    rows: ["Airport lookup", "City codes", "Travel category lookup", "Emission factors"],
  },
];

export default function SourcesLookups() {
  return (
    <div>
      <PageHeader
        title="Sources / Lookups"
        description="Reference data that lets ingestion turn source-system rows into understandable ESG activity records."
      />

      <div className="grid gap-4 lg:grid-cols-3">
        {sources.map((source) => (
          <section key={source.title} className="card p-5">
            <h2 className="text-base font-semibold text-slate-950">{source.title}</h2>
            <ul className="mt-4 space-y-2">
              {source.rows.map((row) => (
                <li key={row} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
                  {row}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
