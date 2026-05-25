import { Link, Outlet, useLocation } from "react-router-dom";
import Sidebar from "./Sidebar";

export default function AppShell() {
  const location = useLocation();

  return (
    <div className="min-h-full bg-slate-100 text-slate-900">
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
            <div className="flex h-16 items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
              <div className="flex min-w-0 items-center gap-3 lg:hidden">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-600 text-xs font-bold text-white">
                  BE
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-slate-950">Breathe ESG</div>
                  <div className="text-xs text-slate-500">Analyst workstation</div>
                </div>
              </div>
              <div className="hidden min-w-0 lg:block">
                <div className="text-xs font-semibold uppercase text-slate-500">Current tenant</div>
                <div className="truncate text-sm font-semibold text-slate-950">Demo Enterprise Client</div>
              </div>
              <div className="flex items-center gap-2">
                <Link
                  to="/ingestion"
                  className="hidden rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 sm:inline-flex"
                >
                  Ingest data
                </Link>
                <Link
                  to="/review"
                  className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700"
                >
                  Review queue
                </Link>
              </div>
            </div>
            <nav className="flex gap-1 overflow-x-auto border-t border-slate-100 px-4 py-2 lg:hidden">
              {[
                ["/", "Overview"],
                ["/ingestion", "Ingestion"],
                ["/ingestion/batches", "Batches"],
                ["/review", "Review"],
                ["/sources", "Sources"],
              ].map(([to, label]) => (
                <Link
                  key={to}
                  to={to}
                  className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold ${
                    location.pathname === to ? "bg-emerald-50 text-emerald-800" : "text-slate-600"
                  }`}
                >
                  {label}
                </Link>
              ))}
            </nav>
          </header>
          <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
