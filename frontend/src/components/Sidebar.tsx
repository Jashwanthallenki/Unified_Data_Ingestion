import { Link, useLocation } from "react-router-dom";
import { cx } from "../lib/format";

const navItems = [
  { label: "Overview", to: "/", section: "home" },
  { label: "Ingestion", to: "/ingestion", section: "ingestion" },
  { label: "Batches", to: "/ingestion/batches", section: "batches" },
  { label: "Analyst Review", to: "/review", section: "review" },
  { label: "Locked Records", to: "/review/activities?locked=true", section: "locked" },
  { label: "Sources / Lookups", to: "/sources", section: "sources" },
];

export default function Sidebar() {
  const location = useLocation();

  function isActive(section: string) {
    if (section === "home") return location.pathname === "/";
    if (section === "batches") return location.pathname.startsWith("/ingestion/batches");
    if (section === "ingestion") return location.pathname === "/ingestion" || location.pathname.startsWith("/ingestion/upload") || location.pathname.startsWith("/ingestion/travel-sync");
    if (section === "review") return location.pathname === "/review" || (location.pathname.startsWith("/review/activities") && !location.search.includes("locked=true"));
    if (section === "locked") return location.pathname === "/review/activities" && location.search.includes("locked=true");
    if (section === "sources") return location.pathname.startsWith("/sources");
    return false;
  }

  return (
    <aside className="hidden w-72 shrink-0 border-r border-slate-200 bg-white lg:flex lg:flex-col">
      <div className="flex h-16 items-center gap-3 border-b border-slate-200 px-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600 text-sm font-bold text-white">
          BE
        </div>
        <div>
          <div className="text-sm font-semibold text-slate-950">Breathe ESG</div>
          <div className="text-xs text-slate-500">Analyst workstation</div>
        </div>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => (
          <Link
            key={item.label}
            to={item.to}
            className={cx(
              "flex items-center justify-between rounded-xl px-3 py-2.5 text-sm font-medium transition",
              isActive(item.section)
                ? "bg-emerald-50 text-emerald-800"
                : "text-slate-600 hover:bg-slate-50 hover:text-slate-950",
            )}
          >
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>
      <div className="border-t border-slate-200 p-4">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
          <div className="text-xs font-semibold uppercase text-slate-500">Tenant</div>
          <div className="mt-1 text-sm font-semibold text-slate-900">Demo Enterprise Client</div>
        </div>
      </div>
    </aside>
  );
}
