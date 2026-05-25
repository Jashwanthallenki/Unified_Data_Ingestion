import { Link, useLocation } from "react-router-dom";
import { cx } from "../lib/format";

function labelFor(pathname: string, segment: string, index: number, parts: string[]) {
  if (pathname === "/" && index === 0) return "Overview";
  if (segment === "ingestion") return "Ingestion";
  if (segment === "upload") return "Guided upload";
  if (segment === "travel-sync") return "Travel sync";
  if (segment === "batches") return "Batches";
  if (segment === "review") return "Analyst review";
  if (segment === "activities") return "Activity records";
  if (segment === "sources") return "Sources / Lookups";
  if (index > 0 && parts[index - 1] === "batches") return "Batch details";
  if (index > 0 && parts[index - 1] === "activities") return "Record details";
  return segment.replace(/-/g, " ");
}

export default function Breadcrumbs({ className }: { className?: string }) {
  const { pathname } = useLocation();
  const parts = pathname === "/" ? [""] : pathname.split("/").filter(Boolean);

  const crumbs = parts.map((part, index) => {
    const href = part === "" ? "/" : `/${parts.slice(0, index + 1).join("/")}`;
    return {
      href,
      label: labelFor(pathname, part, index, parts),
    };
  });

  return (
    <nav className={cx("flex flex-wrap items-center gap-1 text-sm text-slate-500", className)} aria-label="Breadcrumb">
      {crumbs.map((crumb, index) => {
        const isLast = index === crumbs.length - 1;
        return (
          <span key={`${crumb.href}-${index}`} className="inline-flex items-center gap-1">
            {index > 0 ? <span className="text-slate-300">/</span> : null}
            {isLast ? (
              <span className="font-medium text-slate-700 capitalize">{crumb.label}</span>
            ) : (
              <Link to={crumb.href} className="hover:text-emerald-700 capitalize">
                {crumb.label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
