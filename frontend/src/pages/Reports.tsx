import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../main";
import { btnCls, btnSmCls, Card, dollars, Error, inputCls, Page, thisMonth, useGet } from "./_shared";

const REPORT_TYPES = ["spending", "trends", "net_worth", "category_trends"];

function MonthReport({ month }: any) {
  const data = useGet(`/api/reports/${month}`);
  const categories = useGet("/api/categories?limit=500");
  const catById = Object.fromEntries(((categories as any)?.items || []).map((c: any) => [c.id, c.name]));
  if (!data || data.error) return <Error data={data} />;
  const spend = [...(data.spend_by_category || [])].sort(
    (a: any, b: any) => Math.abs(b.total_cents) - Math.abs(a.total_cents));
  const chart = spend.slice(0, 10).map((s: any) => ({
    name: catById[s.category_id] || "Uncategorized",
    total: Math.abs(s.total_cents) / 100,
  }));
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <Card title="Cash"><p className="text-xl font-semibold">{dollars(data.net_worth?.cash_cents)}</p></Card>
        <Card title="Investments"><p className="text-xl font-semibold">{dollars(data.net_worth?.investments_cents)}</p></Card>
        <Card title="Net worth"><p className="text-xl font-semibold">{dollars(data.net_worth?.net_worth_cents)}</p></Card>
      </div>
      {chart.length > 0 && (
        <Card title="Top categories">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chart} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" tickFormatter={(v: number) => `$${v}`} />
              <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v: any) => `$${Number(v).toLocaleString()}`} />
              <Bar dataKey="total" fill="#0f172a" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}
      <Card title="Spend by category">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-slate-500">
              <th className="py-1">Category</th><th className="text-right">Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {spend.map((s: any) => (
              <tr key={s.category_id ?? "none"}>
                <td className="py-1">{catById[s.category_id] || "Uncategorized"}</td>
                <td className="text-right">{dollars(s.total_cents)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function Trends() {
  const data = useGet("/api/reports-trends?months=12");
  if (!data || data.error) return <Error data={data} />;
  const rows = (Array.isArray(data) ? data : []).map((m: any) => ({
    ...m, income: m.income_cents / 100, expense: m.expense_cents / 100, net: m.net_cents / 100,
  }));
  return (
    <Card title="Income vs expenses (12 mo)">
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="month" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} />
          <Tooltip formatter={(v: any) => `$${Number(v).toLocaleString()}`} />
          <Line type="monotone" dataKey="income" stroke="#15803d" dot={false} />
          <Line type="monotone" dataKey="expense" stroke="#b91c1c" dot={false} />
          <Line type="monotone" dataKey="net" stroke="#0f172a" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </Card>
  );
}

function NetWorth({ tick, bump }: any) {
  const data = useGet(`/api/net-worth-history?tick=${tick}`);
  const [msg, setMsg] = useState("");
  async function snap() {
    try {
      const r = await api("/api/snapshots/run", { method: "POST" });
      setMsg(`Snapshot ${r.date}: ${dollars(r.net_worth_cents)}.`);
      bump();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  const rows = (Array.isArray(data) ? data : []).map((s: any) => ({ ...s, net: s.net_worth_cents / 100 }));
  return (
    <Card title="Net worth history">
      <div className="mb-3 flex items-center gap-2">
        <button onClick={snap} className={btnCls}>Record snapshot</button>
        {msg && <span className="text-sm text-slate-600">{msg}</span>}
      </div>
      <Error data={data} />
      {rows.length === 0 ? (
        <p className="text-sm text-slate-500">No snapshots yet — record one above.</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={rows}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} />
            <Tooltip formatter={(v: any) => `$${Number(v).toLocaleString()}`} />
            <Line type="monotone" dataKey="net" stroke="#0f172a" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}

function SavedReports() {
  const [tick, setTick] = useState(0);
  const [msg, setMsg] = useState("");
  const data = useGet(`/api/saved-reports?tick=${tick}`);
  const items = Array.isArray(data) ? data : [];
  const [name, setName] = useState("");
  const [type, setType] = useState("spending");
  const [month, setMonth] = useState(thisMonth());

  async function save(e: any) {
    e.preventDefault();
    if (!name.trim()) { setMsg("Name is required."); return; }
    try {
      await api("/api/saved-reports", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), type, params: type === "spending" ? { month } : {} }),
      });
      setName(""); setMsg("");
      setTick((t) => t + 1);
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  async function run(id: number) {
    try {
      const r = await api(`/api/saved-reports/${id}/run`, { method: "POST" });
      setMsg(`Ran #${id}: ${JSON.stringify(r).slice(0, 160)}…`);
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  async function del(id: number) {
    if (!window.confirm(`Delete saved report #${id}?`)) return;
    await api(`/api/saved-reports/${id}`, { method: "DELETE" });
    setTick((t) => t + 1);
  }

  return (
    <Card title={`Saved reports (${items.length})`}>
      <form onSubmit={save} className="mb-3 flex flex-wrap items-end gap-2">
        <label className="text-sm">Name
          <input value={name} onChange={(e) => setName(e.target.value)} className={`${inputCls} ml-1 w-44`} />
        </label>
        <label className="text-sm">Type
          <select value={type} onChange={(e) => setType(e.target.value)} className={`${inputCls} ml-1`}>
            {REPORT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        {type === "spending" && (
          <label className="text-sm">Month
            <input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)}
              className={`${inputCls} ml-1`} />
          </label>
        )}
        <button className={btnCls}>Save report</button>
        {msg && <span className="text-sm text-slate-600">{msg}</span>}
      </form>
      <Error data={data} />
      {items.length === 0 ? (
        <p className="text-sm text-slate-500">None saved yet.</p>
      ) : (
        <ul className="divide-y divide-slate-100 text-sm">
          {items.map((r: any) => (
            <li key={r.id} className="flex items-center justify-between py-1">
              <span>{r.name} · {r.type} · {JSON.stringify(r.params)}</span>
              <span className="space-x-1">
                <button onClick={() => run(r.id)} className={btnSmCls}>Run</button>
                <button onClick={() => del(r.id)} className={btnSmCls}>Delete</button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function Reports() {
  const [month, setMonth] = useState(thisMonth());
  const [tick, setTick] = useState(0);
  return (
    <Page title="Reports">
      <Card title="Month">
        <input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)}
          className={inputCls} />
      </Card>
      <MonthReport month={month} />
      <Trends />
      <NetWorth tick={tick} bump={() => setTick((t) => t + 1)} />
      <SavedReports />
    </Page>
  );
}
