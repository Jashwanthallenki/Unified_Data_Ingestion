import type { ReactNode } from "react";
import {
  cx,
  friendlyEligibility,
  friendlyFlag,
  friendlyMethod,
  friendlyReviewStatus,
  friendlySource,
  humanize,
  sourceAccent,
} from "../lib/format";

function Pill({ className, children, title }: { className: string; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold leading-none",
        className,
      )}
    >
      {children}
    </span>
  );
}

const STATUS_COLORS: Record<string, string> = {
  COMPLETE: "border-emerald-200 bg-emerald-50 text-emerald-700",
  PARTIAL: "border-amber-200 bg-amber-50 text-amber-800",
  FAILED: "border-rose-200 bg-rose-50 text-rose-700",
  PROCESSING: "border-blue-200 bg-blue-50 text-blue-700",
};

const CONFIDENCE_COLORS: Record<string, string> = {
  HIGH: "border-emerald-200 bg-emerald-50 text-emerald-700",
  MEDIUM: "border-amber-200 bg-amber-50 text-amber-800",
  LOW: "border-orange-200 bg-orange-50 text-orange-800",
  FAILED: "border-rose-200 bg-rose-50 text-rose-700",
};

const ELIGIBILITY_COLORS: Record<string, string> = {
  ELIGIBLE: "border-emerald-200 bg-emerald-50 text-emerald-700",
  NEEDS_REVIEW: "border-amber-200 bg-amber-50 text-amber-800",
  NOT_RELEVANT: "border-slate-200 bg-slate-50 text-slate-600",
  EXCLUDED: "border-slate-200 bg-slate-50 text-slate-600",
  FAILED: "border-rose-200 bg-rose-50 text-rose-700",
};

const REVIEW_COLORS: Record<string, string> = {
  PENDING: "border-amber-200 bg-amber-50 text-amber-800",
  APPROVED: "border-emerald-200 bg-emerald-50 text-emerald-700",
  REJECTED: "border-rose-200 bg-rose-50 text-rose-700",
  CLARIFICATION_REQUESTED: "border-blue-200 bg-blue-50 text-blue-700",
  MARKED_NOT_RELEVANT: "border-slate-200 bg-slate-50 text-slate-600",
  LOCKED: "border-emerald-200 bg-emerald-50 text-emerald-700",
};

const FLAG_COLORS: Record<string, string> = {
  SPEND_BASED_FALLBACK: "border-amber-200 bg-amber-50 text-amber-800",
  ESTIMATED_READING: "border-blue-200 bg-blue-50 text-blue-700",
  LLM_SUGGESTED_FIELD: "border-purple-200 bg-purple-50 text-purple-700",
  LLM_SUGGESTION_FAILED: "border-purple-200 bg-purple-50 text-purple-700",
  SUSPICIOUS_HIGH_QUANTITY: "border-rose-200 bg-rose-50 text-rose-700",
  USAGE_SPIKE_AFTER_DAY_NORMALIZATION: "border-rose-200 bg-rose-50 text-rose-700",
  DUPLICATE_DOCUMENT: "border-orange-200 bg-orange-50 text-orange-700",
  POSSIBLE_CODESHARE_DUPLICATE: "border-orange-200 bg-orange-50 text-orange-700",
  CANCELLED_BOOKING: "border-slate-200 bg-slate-50 text-slate-600",
  REFUNDED_BOOKING: "border-slate-200 bg-slate-50 text-slate-600",
  POSSIBLE_AMENDED_BILL: "border-amber-200 bg-amber-50 text-amber-800",
  GERMAN_HEADER_MAPPING_USED: "border-sky-200 bg-sky-50 text-sky-700",
  PURCHASE_NOT_CONSUMPTION: "border-amber-200 bg-amber-50 text-amber-800",
  BUNDLED_TRAVEL_PACKAGE: "border-amber-200 bg-amber-50 text-amber-800",
  RENTAL_CAR_DOUBLE_COUNT_RISK: "border-orange-200 bg-orange-50 text-orange-700",
  REVERSAL_ROW: "border-sky-200 bg-sky-50 text-sky-700",
  SCRAP_REQUIRES_REVIEW: "border-amber-200 bg-amber-50 text-amber-800",
};

const METHOD_COLORS: Record<string, string> = {
  DIRECT: "border-emerald-200 bg-emerald-50 text-emerald-700",
  RULE_BASED: "border-sky-200 bg-sky-50 text-sky-700",
  LLM_SUGGESTED: "border-purple-200 bg-purple-50 text-purple-700",
  MISSING: "border-rose-200 bg-rose-50 text-rose-700",
  ANALYST_OVERRIDDEN: "border-indigo-200 bg-indigo-50 text-indigo-700",
};

export function StatusBadge({ value }: { value: string }) {
  return <Pill className={STATUS_COLORS[value] || "border-slate-200 bg-slate-50 text-slate-700"}>{humanize(value)}</Pill>;
}

export function ConfidenceBadge({ value }: { value: string }) {
  return (
    <Pill
      className={CONFIDENCE_COLORS[value] || "border-slate-200 bg-slate-50 text-slate-700"}
      title="Confidence score: How complete and trustworthy this row is."
    >
      {humanize(value)} confidence
    </Pill>
  );
}

export function EligibilityBadge({ value }: { value: string }) {
  return <Pill className={ELIGIBILITY_COLORS[value] || "border-slate-200 bg-slate-50 text-slate-700"}>{friendlyEligibility(value)}</Pill>;
}

export function ReviewStatusBadge({ value }: { value: string }) {
  return <Pill className={REVIEW_COLORS[value] || "border-slate-200 bg-slate-50 text-slate-700"}>{friendlyReviewStatus(value)}</Pill>;
}

export function SourceBadge({ value }: { value: string }) {
  return <Pill className={sourceAccent(value)}>{friendlySource(value)}</Pill>;
}

export function FlagBadge({ value }: { value: string }) {
  const tone = FLAG_COLORS[value] || "border-slate-200 bg-slate-50 text-slate-700";
  return <Pill className={tone}>{friendlyFlag(value)}</Pill>;
}

export function MethodBadge({ value }: { value: string }) {
  const tone = METHOD_COLORS[value] || "border-slate-200 bg-slate-50 text-slate-700";
  return (
    <Pill
      className={tone}
      title="Field provenance: Shows whether the value came directly from the source, rules, AI suggestion, or analyst override."
    >
      {friendlyMethod(value)}
    </Pill>
  );
}

export function FlagList({ flags, limit }: { flags: string[]; limit?: number }) {
  if (!flags || !flags.length) return <span className="text-xs text-slate-400">No flags</span>;
  const visible = limit ? flags.slice(0, limit) : flags;
  const hidden = limit && flags.length > limit ? flags.length - limit : 0;
  return (
    <div className="flex flex-wrap gap-1.5">
      {visible.map((flag) => <FlagBadge key={flag} value={flag} />)}
      {hidden ? <Pill className="border-slate-200 bg-slate-50 text-slate-600">+{hidden} more</Pill> : null}
    </div>
  );
}
