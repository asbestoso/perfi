import { useState } from "react";
import { api } from "../main";
import { Amt, Badge, btnCls, btnSmCls, Card, dollars, Empty, Error, inputCls, Page, tblCls, thisMonth, useGet } from "./_shared";

function paceTone(pace: string) {
  return pace === "over" ? "red" : pace === "ahead" ? "amber" : "green";
}

function barTone(pct: number) {
  return pct >= 100 ? "bg-red-500" : pct >= 75 ? "bg-amber-500" : "bg-pine-600";
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
          <Empty>No budgets for this month yet.</Empty>
        ) : (
          <table className={tblCls}>
            <thead>
              <tr>
                <th>Category</th><th className="text-right">Limit</th>
                <th className="text-right">Spent</th><th className="text-right">Remaining</th>
                <th className="text-right">Progress</th><th>Pace</th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((b: any) => {
                const pct = b.effective_cents > 0
                  ? Math.min(100, Math.round((b.spent_cents / b.effective_cents) * 100)) : 0;
                return (
                  <tr key={b.budget_id}>
                    <td className="font-medium">{catById[b.category_id] || `#${b.category_id}`}
                      {b.rolled_cents ? <span className="font-normal text-slate-400"> (+{dollars(b.rolled_cents)} roll)</span> : null}
                    </td>
                    <td className="text-right tabular-nums">{dollars(b.effective_cents)}</td>
                    <td className="text-right tabular-nums">{dollars(b.spent_cents)}</td>
                    <td className="text-right"><Amt cents={b.remaining_cents} /></td>
                    <td>
                      <div className="ml-auto h-2 w-24 overflow-hidden rounded-full bg-slate-100">
                        <div className={`h-full ${barTone(pct)}`} style={{ width: `${pct}%` }} />
                      </div>
                    </td>
                    <td><Badge tone={paceTone(b.pace)}>{b.pace}</Badge></td>
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
