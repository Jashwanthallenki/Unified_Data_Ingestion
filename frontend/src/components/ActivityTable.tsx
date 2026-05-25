import { Link } from "react-router-dom";
import type { NormalizedActivity } from "../api/types";
import {
  ConfidenceBadge,
  FlagList,
  ReviewStatusBadge,
  SourceBadge,
} from "./Badges";
import { EmptyState, LoadingState } from "./States";
import {
  formatActivityDate,
  formatActivityLocation,
  formatNumber,
  formatQuantity,
  friendlyMethod,
  humanize,
} from "../lib/format";

export default function ActivityTable({
  activities,
  loading,
  emptyMessage = "Great - no rows need review right now.",
}: {
  activities: NormalizedActivity[];
  loading: boolean;
  emptyMessage?: string;
}) {
  if (loading) return <LoadingState label="Loading activity records..." />;
  if (!activities.length) {
    return (
      <EmptyState
        title={emptyMessage}
        message="As new ingestion batches create normalized records, anything suspicious or low confidence will appear here."
      />
    );
  }

  return (
    <div className="card overflow-x-auto">
      <table className="table-default min-w-full">
        <thead>
          <tr>
            <th>Source</th>
            <th>Activity</th>
            <th>Facility / location</th>
            <th>Date / period</th>
            <th>Quantity</th>
            <th>Unit</th>
            <th>Confidence</th>
            <th>Flags</th>
            <th>Provenance</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {activities.map((activity) => (
            <tr key={activity.id}>
              <td><SourceBadge value={activity.source_type} /></td>
              <td>
                <div className="font-medium text-slate-900">{humanize(activity.activity_type)}</div>
                <div className="text-xs text-slate-500">{activity.activity_subtype ? humanize(activity.activity_subtype) : "Subtype not set"}</div>
              </td>
              <td>
                <div>{formatActivityLocation(activity)}</div>
                {activity.vendor ? <div className="text-xs text-slate-500">{activity.vendor}</div> : null}
              </td>
              <td>{formatActivityDate(activity)}</td>
              <td>{formatQuantity(activity)}</td>
              <td>{activity.normalized_unit || activity.unit || activity.currency || "Not available"}</td>
              <td>
                <ConfidenceBadge value={activity.confidence_level} />
                <div className="mt-1 text-xs text-slate-500">Score {activity.data_quality_score}</div>
              </td>
              <td className="max-w-72"><FlagList flags={activity.flags} limit={3} /></td>
              <td>
                <div className="text-xs font-medium text-slate-700">{friendlyMethod(activity.calculation_method)}</div>
                {activity.co2e_kg ? <div className="text-xs text-slate-500">{formatNumber(activity.co2e_kg, 1)} kg CO2e</div> : null}
              </td>
              <td><ReviewStatusBadge value={activity.review_status} /></td>
              <td>
                <Link to={`/review/activities/${activity.id}`} className="btn py-1 text-xs">
                  Open record
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
