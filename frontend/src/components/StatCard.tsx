import { Link } from "react-router-dom";
import { cx, formatNumber } from "../lib/format";

const tones: Record<string, string> = {
  green: "border-emerald-200 bg-emerald-50",
  amber: "border-amber-200 bg-amber-50",
  red: "border-rose-200 bg-rose-50",
  purple: "border-purple-200 bg-purple-50",
  blue: "border-blue-200 bg-blue-50",
  gray: "border-slate-200 bg-white",
};

export default function StatCard({
  label,
  value,
  help,
  tone = "gray",
  to,
}: {
  label: string;
  value: number | string;
  help?: string;
  tone?: keyof typeof tones;
  to?: string;
}) {
  const body = (
    <>
      <div className="text-xs font-semibold uppercase text-slate-500">{label}</div>
      <div className="mt-2 text-3xl font-semibold text-slate-950">{typeof value === "number" ? formatNumber(value) : value}</div>
      {help ? <div className="mt-2 text-xs leading-5 text-slate-600">{help}</div> : null}
    </>
  );

  const className = cx(
    "rounded-xl border p-4 shadow-sm transition",
    tones[tone],
    to && "hover:-translate-y-0.5 hover:shadow-md",
  );

  if (to) {
    return (
      <Link to={to} className={className}>
        {body}
      </Link>
    );
  }

  return <div className={className}>{body}</div>;
}
