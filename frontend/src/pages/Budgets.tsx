import { useState } from "react";
import { api } from "../main";
import { btnCls, btnSmCls, Card, dollars, Error, inputCls, Page, thisMonth, useGet } from "./_shared";

function paceBadge(pace: string) {
  const color = pace === "over" ? "bg-red-100 text-red-800"
    : pace === "ahead" ? "bg-amber-100 text-amber-800"
    : "bg-green-100 text-green-800";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>{pace}</span>;
}

function AddBudget({ month, categories, onDone }: any) {
  const [categoryId, setCategoryId] = useState("");
  const [limit, setLimit] = useState("");
  const [rollover, setRollover] = useState(false);
  const [msg, setMsg] = useState("");
  async function submit(e: any) {
    e.preventDefault();
    if (!categoryId) { setMsg("Pick a category."); return; }
    try {
      await api("/api/budgets", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category_id: Number(categoryId), month,
          limit_cents: Math.round(Number(limit || 0) * 100), rollover,
        }),
      });
      setCategoryId(""); setLimit(""); setRollover(false); setMsg("");
      onDone();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
      <label className="text-sm">Category
        <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}
          className={`${inputCls} ml-1`}>
          <option value="">—</option>
          {(categories?.items || []).map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </label>
      <label className="text-sm">Limit $
        <input value={limit} onChange={(e) => setLimit(e.target.value)} inputMode="decimal"
          placeholder="500" className={`${inputCls} ml-1 w-24`} />
      </label>
      <label className="text-sm">
        <input type="checkbox" checked={rollover} onChange={(e) => setRollover(e.target.checked)}
          className="mr-1" />Rollover
      </label>
      <button className={btnCls}>Add budget</button>
      {msg && <span className="text-sm text-slate-600">{msg}</span>}
    </form>
  );
}

export default function Budgets() {
  const [month, setMonth] = useState(thisMonth());
  const [tick, setTick] = useState(0);
  const bump = () => setTick((t) => t + 1);
  const data = useGet(`/api/budgets/${month}?tick=${tick}`);
  const categories = useGet("/api/categories?limit=500");
  const catById = Object.fromEntries(((categories as any)?.items || []).map((c: any) => [c.id, c.name]));
  const rows = Array.isArray(data) ? data : [];

  async function del(id: number) {
    if (!window.confirm(`Delete budget #${id}?`)) return;
    await api(`/api/budgets/${id}`, { method: "DELETE" });
    bump();
  }

  return (
    <Page title="Budgets">
      <Card title="Month">
        <input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)}
          className={inputCls} />
      </Card>
      <Card title="Add budget">
        <AddBudget month={month} categories={categories} onDone={bump} />
      </Card>
      <Card title={`${month} · ${rows.length} budgets`}>
        <Error data={rows.length ? null : data} />
        {rows.length === 0 ? (
          <p className="text-sm text-slate-500">No budgets for this month yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-slate-500">
                <th className="py-1">Category</th><th className="text-right">Limit</th>
                <th className="text-right">Spent</th><th className="text-right">Remaining</th>
                <th className="text-right">Progress</th><th>Pace</th><th></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((b: any) => {
                const pct = b.effective_cents > 0
                  ? Math.min(100, Math.round((b.spent_cents / b.effective_cents) * 100)) : 0;
                return (
                  <tr key={b.budget_id}>
                    <td className="py-1">{catById[b.category_id] || `#${b.category_id}`}
                      {b.rolled_cents ? <span className="text-slate-400"> (+{dollars(b.rolled_cents)} roll)</span> : null}
                    </td>
                    <td className="text-right">{dollars(b.effective_cents)}</td>
                    <td className="text-right">{dollars(b.spent_cents)}</td>
                    <td className={`text-right ${b.remaining_cents < 0 ? "text-red-700" : ""}`}>
                      {dollars(b.remaining_cents)}
                    </td>
                    <td className="text-right">
                      <div className="ml-auto h-2 w-24 overflow-hidden rounded-full bg-slate-100">
                        <div className={`h-full ${pct >= 100 ? "bg-red-500" : "bg-slate-700"}`}
                          style={{ width: `${pct}%` }} />
                      </div>
                    </td>
                    <td>{paceBadge(b.pace)}</td>
                    <td className="text-right">
                      <button onClick={() => del(b.budget_id)} className={btnSmCls}>Delete</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </Page>
  );
}
