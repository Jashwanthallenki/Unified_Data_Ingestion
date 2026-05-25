import type { IngestionBatch, NormalizedActivity } from "../api/types";

export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export function humanize(value: string | null | undefined) {
  if (!value) return "Not available";
  return value
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function friendlySource(source: string | null | undefined) {
  const sources: Record<string, string> = {
    sap: "SAP",
    utility: "Utility",
    travel: "Travel",
  };
  return source ? sources[source] || humanize(source) : "Unknown source";
}

export function sourceAccent(source: string | null | undefined) {
  const accents: Record<string, string> = {
    sap: "border-emerald-200 bg-emerald-50 text-emerald-800",
    utility: "border-blue-200 bg-blue-50 text-blue-800",
    travel: "border-violet-200 bg-violet-50 text-violet-800",
  };
  return accents[source || ""] || "border-slate-200 bg-slate-50 text-slate-700";
}

export function friendlyFlag(flag: string | null | undefined) {
  const flags: Record<string, string> = {
    UNKNOWN_UNIT: "Unknown unit",
    ESTIMATED_READING: "Estimated meter reading",
    LLM_SUGGESTED_FIELD: "AI suggestion available",
    SPEND_BASED_FALLBACK: "Spend-based estimate",
    SUSPICIOUS_HIGH_QUANTITY: "Suspicious high quantity",
    USAGE_SPIKE_AFTER_DAY_NORMALIZATION: "Usage spike",
    DUPLICATE_DOCUMENT: "Duplicate document",
    POSSIBLE_CODESHARE_DUPLICATE: "Possible codeshare duplicate",
    CANCELLED_BOOKING: "Cancelled booking",
    REFUNDED_BOOKING: "Refunded booking",
    POSSIBLE_AMENDED_BILL: "Possible amended bill",
    GERMAN_HEADER_MAPPING_USED: "German headers detected",
    PURCHASE_NOT_CONSUMPTION: "Purchase, not consumption",
    BUNDLED_TRAVEL_PACKAGE: "Bundled travel package",
    RENTAL_CAR_DOUBLE_COUNT_RISK: "Rental car double-count risk",
    REVERSAL_ROW: "Reversal row",
    SCRAP_REQUIRES_REVIEW: "Scrap requires review",
    LLM_SUGGESTION_FAILED: "AI suggestion failed",
  };
  return flag ? flags[flag] || humanize(flag) : "No flag";
}

export function friendlyReviewStatus(status: string | null | undefined) {
  const statuses: Record<string, string> = {
    PENDING: "Pending review",
    APPROVED: "Approved",
    REJECTED: "Rejected",
    CLARIFICATION_REQUESTED: "Clarification requested",
    MARKED_NOT_RELEVANT: "Marked not relevant",
    LOCKED: "Locked",
  };
  return status ? statuses[status] || humanize(status) : "Unknown";
}

export function friendlyEligibility(status: string | null | undefined) {
  const statuses: Record<string, string> = {
    ELIGIBLE: "ESG relevant",
    NEEDS_REVIEW: "Needs analyst review",
    NOT_RELEVANT: "Not ESG relevant",
    EXCLUDED: "Intentionally excluded",
    FAILED: "Could not process",
  };
  return status ? statuses[status] || humanize(status) : "Unknown relevance";
}

export function friendlyMethod(method: string | null | undefined) {
  const methods: Record<string, string> = {
    DIRECT: "Direct from source",
    RULE_BASED: "Rule based",
    LLM_SUGGESTED: "AI suggested",
    MISSING: "Missing",
    ANALYST_OVERRIDDEN: "Analyst override",
    spend_based: "Spend based",
    quantity_based: "Quantity based",
    distance_based: "Distance based",
  };
  return method ? methods[method] || humanize(method) : "Not available";
}

export function friendlyExclusion(reason: string | null | undefined) {
  const reasons: Record<string, string> = {
    movement_type_101_receipt: "Receipt row excluded to avoid counting purchases as consumption",
    movement_type_311_transfer: "Transfer row excluded because it moved stock internally",
    movement_type_301_transfer: "Transfer row excluded because it moved stock internally",
    movement_type_561_initial_stock: "Initial stock row excluded because it is not consumption",
    cancelled_flight: "Cancelled flight excluded",
    refunded_booking: "Refunded booking excluded",
    voided_booking: "Voided booking excluded",
    tax_only_utility_row: "Tax-only utility row excluded",
    late_fee_only_utility_row: "Late-fee utility row excluded",
    amount_only_no_usage: "Amount-only row excluded because no usage was present",
    refund_utility_row: "Refund utility row excluded",
    gas_rejected_for_electricity_adapter: "Gas row excluded from electricity ingestion",
    expense_only_no_travel_segment: "Expense-only row excluded because it has no travel segment",
  };
  return reason ? reasons[reason] || humanize(reason) : "No reason recorded";
}

export function issueWhyItMatters(code: string) {
  if (code.includes("UNIT")) return "The emissions math depends on a trusted unit conversion.";
  if (code.includes("MISSING")) return "Missing source data lowers confidence and may need analyst context.";
  if (code.includes("DUPLICATE")) return "Duplicate records can overstate emissions if they are counted twice.";
  if (code.includes("SUSPICIOUS") || code.includes("SPIKE")) return "Outliers may be real, but they need confirmation before audit lock.";
  if (code.includes("LLM")) return "AI assistance is advisory and must be reviewed by an analyst.";
  if (code.includes("OVERLAP") || code.includes("AMENDED")) return "Overlapping periods may represent amended bills or double counting.";
  return "This issue affects whether the activity record can be trusted for reporting.";
}

export function formatDate(value: string | null | undefined) {
  if (!value) return "Not available";
  return value;
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function shortId(id: string | null | undefined) {
  if (!id) return "Not available";
  return id.slice(0, 8);
}

export function formatNumber(value: number | string | null | undefined, digits = 0) {
  if (value === null || value === undefined || value === "") return "Not available";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function formatQuantity(activity: NormalizedActivity) {
  if (activity.normalized_quantity) {
    return `${formatNumber(activity.normalized_quantity, 2)} ${activity.normalized_unit || ""}`.trim();
  }
  if (activity.quantity) {
    return `${formatNumber(activity.quantity, 2)} ${activity.unit || ""}`.trim();
  }
  if (activity.amount) {
    return `${formatNumber(activity.amount, 2)} ${activity.currency || ""}`.trim();
  }
  return "Not available";
}

export function formatActivityLocation(activity: NormalizedActivity) {
  if (activity.source_type === "travel") {
    return activity.origin || activity.destination
      ? `${activity.origin || "Unknown"} to ${activity.destination || "Unknown"}`
      : activity.facility_name || "Travel location unavailable";
  }
  return activity.facility_name || activity.facility_code || activity.vendor || "Location unavailable";
}

export function formatActivityDate(activity: NormalizedActivity) {
  if (activity.period_start && activity.period_end) {
    return `${activity.period_start} to ${activity.period_end}`;
  }
  return activity.activity_date || activity.calendar_month || "Date unavailable";
}

export function batchSourceLabel(batch: IngestionBatch) {
  if (batch.original_filename) return batch.original_filename;
  if (batch.api_sync_range_start || batch.api_sync_range_end) {
    return `${batch.api_sync_range_start || "Start"} to ${batch.api_sync_range_end || "End"}`;
  }
  return "API sync";
}

export function getBatchReviewNeed(batch: IngestionBatch) {
  return batch.low_confidence_rows + batch.suspicious_rows + batch.llm_suggested_rows;
}
