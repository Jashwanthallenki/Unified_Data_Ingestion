import { NavLink } from "react-router-dom";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 text-sm font-medium rounded-md ${
    isActive ? "bg-brand-100 text-brand-700" : "text-slate-600 hover:bg-slate-100"
  }`;

export default function Nav() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="max-w-7xl mx-auto px-4 flex items-center h-14 gap-2">
        <div className="flex items-center gap-2 mr-6">
          <div className="w-7 h-7 rounded-md bg-brand-600 text-white flex items-center justify-center font-bold text-sm">
            BE
          </div>
          <span className="font-semibold text-slate-800">Breathe ESG</span>
          <span className="ml-1 text-xs text-slate-400">prototype</span>
        </div>
        <nav className="flex items-center gap-1">
          <NavLink to="/ingestion" className={linkClass}>Ingestion</NavLink>
          <NavLink to="/ingestion/batches" className={linkClass}>Batches</NavLink>
          <NavLink to="/review" end className={linkClass}>Review summary</NavLink>
          <NavLink to="/review/activities" className={linkClass}>Activities</NavLink>
        </nav>
        <div className="ml-auto text-xs text-slate-500">
          Tenant: <span className="font-medium text-slate-700">Demo Enterprise Client</span>
        </div>
      </div>
    </header>
  );
}
