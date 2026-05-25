import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { reviewSummary } from "../../api/client";
import type { ReviewSummary as ReviewSummaryT } from "../../api/types";
import PageHeader from "../../components/PageHeader";
import StatCard from "../../components/StatCard";
import { EmptyState, ErrorState, LoadingState } from "../../components/States";

export default function Summary() {
  const [summary, setSummary] = useState<ReviewSummaryT | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    reviewSummary()
      .then(setSummary)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState label="Loading analyst review dashboard..." />;
  if (error) return <ErrorState message={error} />;
  if (!summary) {
    return <EmptyState title="Great - no rows need review right now." message="Ingest source data to create activity records for analyst review." />;
  }

  const nextAction = getNextAction(summary);

  return (
    <div>
      <PageHeader
        title="What needs analyst attention?"
        description="Use this dashboard to start with the riskiest records: low confidence, suspicious flags, estimated readings, spend-based rows, or AI suggestions."
        actions={<Link to="/review/activities" className="btn-primary">Open activity queue</Link>}
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Pending review" value={summary.pending} tone="amber" to="/review/activities?status=PENDING" />
        <StatCard label="Low confidence" value={summary.low_confidence} tone="red" to="/review/activities?confidence=LOW" />
        <StatCard label="Suspicious" value={summary.suspicious} tone="red" to="/review/activities?suspicious=true" />
        <StatCard label="AI suggested" value={summary.llm_suggested} tone="purple" to="/review/activities?flag=LLM_SUGGESTED_FIELD" />
        <StatCard label="Estimated readings" value={summary.estimated} tone="blue" to="/review/activities?flag=ESTIMATED_READING" />
        <StatCard label="Spend-based" value={summary.spend_based} tone="amber" to="/review/activities?flag=SPEND_BASED_FALLBACK" />
        <StatCard label="Approved" value={summary.approved} tone="green" to="/review/activities?status=APPROVED" />
        <StatCard label="Locked" value={summary.locked} tone="green" to="/review/activities?locked=true" />
      </div>

      <section className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 p-5 shadow-sm">
        <div className="text-xs font-semibold uppercase text-emerald-700">Recommended next action</div>
        <h2 className="mt-2 text-lg font-semibold text-emerald-950">{nextAction.title}</h2>
        <p className="mt-2 text-sm leading-6 text-emerald-900">{nextAction.description}</p>
        <Link to={nextAction.to} className="btn-primary mt-4">
          {nextAction.cta}
        </Link>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card p-5">
          <h2 className="text-base font-semibold text-slate-950">Review outcomes</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <StatCard label="Rejected" value={summary.rejected} tone="red" to="/review/activities?status=REJECTED" />
            <StatCard label="Clarification requested" value={summary.clarification_requested} tone="blue" to="/review/activities?status=CLARIFICATION_REQUESTED" />
            <StatCard label="Marked not relevant" value={summary.marked_not_relevant} tone="gray" to="/review/activities?status=MARKED_NOT_RELEVANT" />
            <StatCard label="Total activity records" value={summary.total} to="/review/activities" />
          </div>
        </section>

        <section className="card p-5">
          <h2 className="text-base font-semibold text-slate-950">Activity records by source</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <StatCard label="SAP" value={summary.by_source.sap} to="/review/activities?source=sap" />
            <StatCard label="Utility" value={summary.by_source.utility} to="/review/activities?source=utility" />
            <StatCard label="Travel" value={summary.by_source.travel} to="/review/activities?source=travel" />
          </div>
        </section>
      </div>
    </div>
  );
}

function getNextAction(summary: ReviewSummaryT) {
  if (summary.llm_suggested > 0) {
    return {
      title: `Start with ${summary.llm_suggested} rows with AI suggestions.`,
      description: "AI suggestions are not final until accepted by an analyst, so these rows are quick wins for focused review.",
      to: "/review/activities?flag=LLM_SUGGESTED_FIELD",
      cta: "Review AI suggestions",
    };
  }
  if (summary.low_confidence > 0) {
    return {
      title: `Start with ${summary.low_confidence} low-confidence rows.`,
      description: "Low-confidence records usually need the most analyst judgment before approval.",
      to: "/review/activities?confidence=LOW",
      cta: "Review low-confidence rows",
    };
  }
  if (summary.suspicious > 0) {
    return {
      title: `Investigate ${summary.suspicious} suspicious rows.`,
      description: "Suspicious rows may be valid outliers, but they should be confirmed before audit lock.",
      to: "/review/activities?suspicious=true",
      cta: "Review suspicious rows",
    };
  }
  return {
    title: "Great - no urgent rows need review right now.",
    description: "You can inspect pending records or move approved rows toward audit lock.",
    to: "/review/activities?status=PENDING",
    cta: "Open pending rows",
  };
}
