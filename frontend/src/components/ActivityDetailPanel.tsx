import type { NormalizedActivityDetail } from "../api/types";
import type { ReactNode } from "react";
import { ConfidenceBadge, EligibilityBadge, FlagList, ReviewStatusBadge, SourceBadge } from "./Badges";
import {
  formatActivityDate,
  formatActivityLocation,
  formatNumber,
  formatQuantity,
  friendlyMethod,
} from "../lib/format";

function TrustItem({ label, value, title }: { label: string; value: ReactNode; title?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" title={title}>
      <div className="text-xs font-semibold uppercase text-slate-500">{label}</div>
      <div className="mt-2 text-sm font-semibold text-slate-900">{value}</div>
    </div>
  );
}

export default function ActivityDetailPanel({ activity }: { activity: NormalizedActivityDetail }) {
  return (
    <div className="space-y-4">
      <div className="card p-5">
        <div className="flex flex-wrap items-center gap-2">
          <SourceBadge value={activity.source_type} />
          <ConfidenceBadge value={activity.confidence_level} />
          <EligibilityBadge value={activity.eligibility_status} />
          <ReviewStatusBadge value={activity.review_status} />
          <FlagList flags={activity.flags} limit={4} />
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-4">
          <TrustItem
            label="Confidence score"
            value={`${activity.data_quality_score}/100`}
            title="Confidence score: How complete and trustworthy this row is."
          />
          <TrustItem label="Review status" value={<ReviewStatusBadge value={activity.review_status} />} />
          <TrustItem label="ESG relevance" value={<EligibilityBadge value={activity.eligibility_status} />} />
          <TrustItem label="Source of truth" value={activity.source_of_truth || "Not available"} />
          <TrustItem label="Calculation method" value={friendlyMethod(activity.calculation_method)} />
          <TrustItem label="Emission method" value={friendlyMethod(activity.emission_method)} />
          <TrustItem
            label="Activity quantity"
            value={formatQuantity(activity)}
          />
          <TrustItem
            label="Estimated emissions"
            value={activity.co2e_kg ? `${formatNumber(activity.co2e_kg, 2)} kg CO2e` : "Not available"}
          />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card p-4">
          <div className="text-xs font-semibold uppercase text-slate-500">Activity</div>
          <div className="mt-2 text-base font-semibold text-slate-900">{activity.activity_type}</div>
          <div className="text-sm text-slate-600">{activity.activity_subtype || "Subtype not set"}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs font-semibold uppercase text-slate-500">Facility / location</div>
          <div className="mt-2 text-base font-semibold text-slate-900">{formatActivityLocation(activity)}</div>
          <div className="text-sm text-slate-600">{activity.facility_country || activity.vendor || "Additional location context unavailable"}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs font-semibold uppercase text-slate-500">Date / period</div>
          <div className="mt-2 text-base font-semibold text-slate-900">{formatActivityDate(activity)}</div>
          <div className="text-sm text-slate-600">{activity.billing_days ? `${activity.billing_days} billing days` : "Single activity date or month"}</div>
        </div>
      </div>
    </div>
  );
}
