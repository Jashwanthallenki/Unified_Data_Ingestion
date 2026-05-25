import { Link } from "react-router-dom";
import PageHeader from "../components/PageHeader";

const steps = [
  {
    title: "Step 1: Ingest source data",
    description: "Upload SAP or utility files, or sync travel data from the mocked corporate travel API.",
  },
  {
    title: "Step 2: Normalize and validate",
    description: "Adapters preserve original rows, apply source-specific rules, and create activity records.",
  },
  {
    title: "Step 3: Review suspicious rows",
    description: "Analysts focus on low-confidence, suspicious, estimated, or AI-suggested records.",
  },
  {
    title: "Step 4: Lock approved records",
    description: "Approved records can be locked with provenance, flags, and emission factor snapshots.",
  },
];

const cards = [
  { title: "Start SAP Upload", description: "Bring in MB51 or ME2M CSV data.", to: "/ingestion/upload?source=sap" },
  { title: "Start Utility Upload", description: "Normalize electricity billing exports.", to: "/ingestion/upload?source=utility" },
  { title: "Sync Travel Data", description: "Pull flights, hotels, cars, and rail from the mock API.", to: "/ingestion/travel-sync" },
  { title: "Open Review Queue", description: "See records that need analyst attention.", to: "/review" },
];

export default function Home() {
  return (
    <div>
      <PageHeader
        title="Overview"
        description="Move from source ingestion to trusted ESG activity records without losing sight of what happened to each row."
      />

      <section className="grid gap-4 lg:grid-cols-4">
        {steps.map((step, index) => (
          <article key={step.title} className="card p-5">
            <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-sm font-bold text-emerald-700">
              {index + 1}
            </div>
            <h2 className="text-base font-semibold text-slate-950">{step.title}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">{step.description}</p>
          </article>
        ))}
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <Link key={card.title} to={card.to} className="card p-5 transition hover:-translate-y-0.5 hover:shadow-md">
            <h2 className="text-base font-semibold text-slate-950">{card.title}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">{card.description}</p>
            <div className="mt-4 text-sm font-semibold text-emerald-700">Continue</div>
          </Link>
        ))}
      </section>

      <section className="mt-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-slate-950">How ingestion and review connect</h2>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
          Ingestion creates batches and normalized activity records. Review helps analysts decide whether those
          records are trustworthy enough to approve and lock for audit.
        </p>
      </section>
    </div>
  );
}
