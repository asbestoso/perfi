import { useEffect, useState } from "react";
import { api } from "../main";

export function useGet(path: string) {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    api(path).then(setData).catch((e) => setData({ error: String(e) }));
  }, [path]);
  return data;
}

export function Page({ title, sub, children }: any) {
  return (
    <main className="mx-auto max-w-6xl space-y-5 px-4 py-8 md:px-8">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
        {sub && <p className="mt-1 text-slate-600">{sub}</p>}
      </header>
      {children}
    </main>
  );
}

export function Card({ title, hint, action, children }: any) {
  return (
    <section className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(16,24,32,0.06)]">
      {(title || action) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            {title && <h2 className="text-base font-semibold tracking-tight">{title}</h2>}
            {hint && <p className="mt-0.5 text-sm text-slate-500">{hint}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

/* Big number with label, for dashboard-style stat rows. */
export function Stat({ label, children }: any) {
  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(16,24,32,0.06)]">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-3xl font-bold tracking-tight tabular-nums">{children}</div>
    </div>
  );
}

/* Signed money: red out, pine in, quiet zero. Null renders as an em dash. */
export function Amt({ cents, className = "" }: any) {
  if (cents == null) return <span className="text-slate-400">—</span>;
  const n = Number(cents);
  const tone = n < 0 ? "text-red-700" : n > 0 ? "text-pine-700" : "text-slate-400";
  return <span className={`tabular-nums ${tone} ${className}`}>{dollars(cents)}</span>;
}

const badgeTones: any = {
  green: "bg-pine-100 text-pine-800",
  amber: "bg-amber-100 text-amber-900",
  red: "bg-red-100 text-red-800",
  slate: "bg-slate-200/70 text-slate-700",
};

export function Badge({ tone = "slate", children }: any) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${badgeTones[tone] || badgeTones.slate}`}>
      {children}
    </span>
  );
}

export function Error({ data }: any) {
  if (!data?.error) return null;
  return <p className="text-sm font-medium text-red-700">Failed to load: {data.error}</p>;
}

export function Empty({ children }: any) {
  return (
    <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50/70 px-4 py-6 text-center text-sm text-slate-500">
      {children}
    </p>
  );
}

export function dollars(cents: any) {
  return (Number(cents || 0) / 100).toLocaleString(undefined, {
    style: "currency", currency: "USD",
  });
}

export function today() {
  return new Date().toISOString().slice(0, 10);
}

export const inputCls =
  "rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm shadow-sm outline-none " +
  "focus:border-pine-600 focus:ring-2 focus:ring-pine-100";
export const btnCls =
  "rounded-lg bg-pine-800 px-3.5 py-1.5 text-sm font-medium text-white shadow-sm " +
  "hover:bg-pine-700 disabled:opacity-50";
export const btnSecCls =
  "rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm " +
  "hover:border-slate-400 hover:bg-slate-50 disabled:opacity-50";
export const btnSmCls =
  "rounded-md border border-slate-300 bg-white px-2 py-0.5 text-xs font-medium text-slate-700 " +
  "hover:border-slate-400 hover:bg-slate-50 disabled:opacity-50";
export const btnDangerCls =
  "rounded-lg bg-red-700 px-3.5 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-red-600";
export const tblCls = "ledger w-full text-sm";
