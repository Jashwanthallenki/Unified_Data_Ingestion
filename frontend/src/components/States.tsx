import type { ReactNode } from "react";

export function LoadingState({ label = "Loading analyst workspace..." }: { label?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
      <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-600" />
      <p className="text-sm font-medium text-slate-700">{label}</p>
    </div>
  );
}

export function ErrorState({ title = "Something went wrong", message }: { title?: string; message: string }) {
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50 p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-rose-800">{title}</h2>
      <p className="mt-1 text-sm leading-6 text-rose-700">{message}</p>
    </div>
  );
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center shadow-sm">
      <h2 className="text-base font-semibold text-slate-900">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-600">{message}</p>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}
