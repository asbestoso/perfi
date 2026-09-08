import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../main";
import { Amt, btnCls, btnSmCls, Card, chart, dollars, Error, inputCls, Page, Stat, tblCls, thisMonth, tooltipStyle, useGet } from "./_shared";

const REPORT_TYPES = ["spending", "trends", "net_worth", "category_trends"];

function MonthReport({ month }: any) {
  const data = useGet(`/api/reports/${month}`);
  const categories = useGet("/api/categories?limit=500");
  const catById = Object.fromEntries(((categories as any)?.items || []).map((c: any) => [c.id, c.name]));
  if (!data || data.error) return <Error data={data} />;
  const spend = [...(data.spend_by_category || [])].sort(
    (a: any, b: any) => Math.abs(b.total_cents) - Math.abs(a.total_cents));
  const bars = spend.slice(0, 10).map((s: any) => ({
    name: catById[s.category_id] || "Uncategorized",
    total: Math.abs(s.total_cents) / 100,
  }));
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="Cash">{dollars(data.net_worth?.cash_cents)}</Stat>
        <Stat label="Investments">{dollars(data.net_worth?.investments_cents)}</Stat>
        <Stat label="Net worth">{dollars(data.net_worth?.net_worth_cents)}</Stat>
      </div>
      {bars.length > 0 && (
        <Card title="Top categories">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={bars} layout="vertical">
              <CartesianGrid stroke={chart.grid} horizontal={false} />
              <XAxis type="number" tickFormatter={(v: number) => `$${v}`} tick={{ fontSize: 12, fill: chart.tick }} tickLine={false} axisLine={{ stroke: chart.grid }} />
              <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 12, fill: chart.tick }} tickLine={false} axisLine={false} />
              <Tooltip formatter={(v: any) => `$${Number(v).toLocaleString()}`} contentStyle={tooltipStyle} cursor={{ fill: "#e7ebe6" }} />
              <Bar dataKey="total" fill="#14532b" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}
      <Card title="Spend by category">
        <table className={tblCls}>
          <thead>
            <tr>
              <th>Category</th><th className="text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            {spend.map((s: any) => (
              <tr key={s.category_id ?? "none"}>
                <td className="font-medium">{catById[s.category_id] || "Uncategorized"}</td>
                <td className="text-right"><Amt cents={s.total_cents} /></td>
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
          <CartesianGrid stroke={chart.grid} vertical={false} />
          <XAxis dataKey="month" tick={{ fontSize: 11, fill: chart.tick }} tickLine={false} axisLine={{ stroke: chart.grid }} />
          <YAxis tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} tick={{ fill: chart.tick }} tickLine={false} axisLine={false} width={52} />
          <Tooltip formatter={(v: any) => `$${Number(v).toLocaleString()}`} contentStyle={tooltipStyle} />
          <Line type="monotone" dataKey="income" stroke={chart.income} dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="expense" stroke={chart.expense} dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="net" stroke={chart.net} dot={false} strokeWidth={2} />
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
            <CartesianGrid stroke={chart.grid} vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: chart.tick }} tickLine={false} axisLine={{ stroke: chart.grid }} />
            <YAxis tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} tick={{ fill: chart.tick }} tickLine={false} axisLine={false} width={52} />
            <Tooltip formatter={(v: any) => `$${Number(v).toLocaleString()}`} contentStyle={tooltipStyle} />
            <Line type="monotone" dataKey="net" stroke={chart.net} dot={false} strokeWidth={2.5} />
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
