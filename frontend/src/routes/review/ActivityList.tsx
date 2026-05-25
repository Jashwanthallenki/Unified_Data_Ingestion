import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { listActivities } from "../../api/client";
import type { NormalizedActivity } from "../../api/types";
import ActivityTable from "../../components/ActivityTable";
import PageHeader from "../../components/PageHeader";
import { ErrorState } from "../../components/States";

const filterConfig = [
  { key: "source", label: "Source", options: [["", "All sources"], ["sap", "SAP"], ["utility", "Utility"], ["travel", "Travel"]] },
  {
    key: "status",
    label: "Status",
    options: [["", "All statuses"], ["PENDING", "Pending"], ["APPROVED", "Approved"], ["REJECTED", "Rejected"], ["CLARIFICATION_REQUESTED", "Clarification"], ["LOCKED", "Locked"]],
  },
  { key: "confidence", label: "Confidence", options: [["", "All confidence"], ["HIGH", "High"], ["MEDIUM", "Medium"], ["LOW", "Low"], ["FAILED", "Failed"]] },
  {
    key: "flag",
    label: "Flag type",
    options: [
      ["", "All flags"],
      ["LLM_SUGGESTED_FIELD", "AI suggestion available"],
      ["ESTIMATED_READING", "Estimated meter reading"],
      ["SPEND_BASED_FALLBACK", "Spend-based estimate"],
      ["SUSPICIOUS_HIGH_QUANTITY", "Suspicious high quantity"],
      ["POSSIBLE_AMENDED_BILL", "Possible amended bill"],
      ["UNKNOWN_UNIT", "Unknown unit"],
    ],
  },
];

export default function ActivityList() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activities, setActivities] = useState<NormalizedActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [count, setCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [activityType, setActivityType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  useEffect(() => {
    setLoading(true);
    setError(null);
    const params: Record<string, string> = {};
    for (const [key, value] of searchParams.entries()) {
      if (value) params[key] = value;
    }
    listActivities(params)
      .then((result) => {
        setActivities(result.results);
        setCount(result.count);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [searchParams]);

  const filtered = useMemo(() => {
    return activities.filter((activity) => {
      if (activityType && activity.activity_type !== activityType) return false;
      const date = activity.activity_date || activity.period_start || activity.calendar_month || "";
      if (dateFrom && date && date < dateFrom) return false;
      if (dateTo && date && date > dateTo) return false;
      return true;
    });
  }, [activities, activityType, dateFrom, dateTo]);

  const activityTypes = useMemo(() => {
    return Array.from(new Set(activities.map((activity) => activity.activity_type).filter(Boolean))).sort();
  }, [activities]);

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  }

  return (
    <div>
      <PageHeader
        title="Activity records"
        description="Filter normalized records by source, status, confidence, flags, activity type, and date to decide what needs review first."
      />

      <section className="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-7">
          {filterConfig.map((filter) => (
            <label key={filter.key}>
              <span className="label">{filter.label}</span>
              <select
                value={searchParams.get(filter.key) || ""}
                onChange={(event) => setParam(filter.key, event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                {filter.options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
          ))}
          <label>
            <span className="label">Activity type</span>
            <select
              value={activityType}
              onChange={(event) => setActivityType(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">All activity types</option>
              {activityTypes.map((type) => <option key={type} value={type}>{type}</option>)}
            </select>
          </label>
          <label>
            <span className="label">Date from</span>
            <input
              type="date"
              value={dateFrom}
              onChange={(event) => setDateFrom(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <label>
            <span className="label">Date to</span>
            <input
              type="date"
              value={dateTo}
              onChange={(event) => setDateTo(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="xl:col-span-2">
            <span className="label">Search</span>
            <input
              type="text"
              placeholder="Facility, vendor, reference, route"
              value={searchParams.get("search") || ""}
              onChange={(event) => setParam("search", event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
        </div>
        <p className="mt-3 text-sm text-slate-600">
          Showing {filtered.length} of {count} records returned by the current queue filters.
        </p>
      </section>

      {error ? (
        <ErrorState message={error} />
      ) : (
        <ActivityTable activities={filtered} loading={loading} />
      )}
    </div>
  );
}
