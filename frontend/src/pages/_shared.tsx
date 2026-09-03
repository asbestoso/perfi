import { useEffect, useState } from "react";
import { api } from "../main";

export function useGet(path: string) {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    api(path).then(setData).catch((e) => setData({ error: String(e) }));
  }, [path]);
  return data;
}

export function Page({ title, children }: any) {
  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-6">
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      {children}
    </main>
  );
}

export function Card({ title, children }: any) {
  return (
    <section className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      {title && <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>}
      {children}
    </section>
  );
}

export function Placeholder({ text }: any) {
  return <p className="text-sm text-slate-500">{text || "Coming soon — this page is a placeholder."}</p>;
}

export function dollars(cents: any) {
  return (Number(cents || 0) / 100).toLocaleString(undefined, {
    style: "currency", currency: "USD",
  });
}

export function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function today() {
  return new Date().toISOString().slice(0, 10);
}

export const inputCls = "rounded-md border border-slate-300 px-2 py-1 text-sm";
export const btnCls = "rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700";
export const btnSmCls = "rounded-md border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-100";

export function Error({ data }: any) {
  if (!data?.error) return null;
  return <p className="text-sm text-red-600">Failed to load: {data.error}</p>;
}
