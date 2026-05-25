import type { ValidationIssue } from "../api/types";
import { humanize, issueWhyItMatters } from "../lib/format";
import { EmptyState } from "./States";

const severityTone: Record<string, string> = {
  ERROR: "border-rose-200 bg-rose-50 text-rose-800",
  WARNING: "border-amber-200 bg-amber-50 text-amber-800",
  INFO: "border-blue-200 bg-blue-50 text-blue-800",
};

export default function ValidationIssueList({ issues }: { issues: ValidationIssue[] }) {
  if (!issues.length) {
    return (
      <EmptyState
        title="No validation issues were found."
        message="This record may still need review if it is low confidence, but no explicit validation warnings were raised."
      />
    );
  }

  return (
    <div className="space-y-3">
      {issues.map((issue) => (
        <article key={issue.id} className={`rounded-xl border p-4 shadow-sm ${severityTone[issue.severity] || severityTone.INFO}`}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex rounded-full border border-current px-2.5 py-1 text-xs font-semibold">
              {humanize(issue.severity)}
            </span>
            <span className="font-mono text-xs">{issue.issue_code}</span>
          </div>
          <h3 className="mt-3 text-sm font-semibold">{issue.message || humanize(issue.issue_code)}</h3>
          <p className="mt-1 text-sm opacity-90">{issueWhyItMatters(issue.issue_code)}</p>
        </article>
      ))}
    </div>
  );
}
