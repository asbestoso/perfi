import { useState } from "react";
import { api } from "../main";
import { Amt, btnSmCls, Card, dollars, Empty, Error, inputCls, Page, tblCls, useGet } from "./_shared";

const PAGE_SIZE = 50;

function Filters({ f, set, accounts, categories }: any) {
  const setK = (k: string) => (e: any) => set({ ...f, [k]: e.target.value, offset: 0 });
  return (
    <div className="mb-3 flex flex-wrap items-end gap-2">
      <label className="text-sm">Search
        <input value={f.q} onChange={setK("q")} placeholder="merchant or note"
          className={`${inputCls} ml-1 w-44`} />
      </label>
      <label className="text-sm">Account
        <select value={f.account_id} onChange={setK("account_id")} className={`${inputCls} ml-1`}>
          <option value="">All</option>
          {(accounts?.items || []).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </label>
      <label className="text-sm">Category
        <select value={f.category_id} onChange={setK("category_id")} className={`${inputCls} ml-1`}>
          <option value="">All</option>
          {(categories?.items || []).map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </label>
      <label className="text-sm">From
        <input type="date" value={f.date_from} onChange={setK("date_from")} className={`${inputCls} ml-1`} />
      </label>
      <label className="text-sm">To
        <input type="date" value={f.date_to} onChange={setK("date_to")} className={`${inputCls} ml-1`} />
      </label>
    </div>
  );
}

function TxnTable({ data, acctName, onRecat, onDelete, categories }: any) {
  const rows = data?.items || [];
  if (rows.length === 0) return <Empty>No transactions match.</Empty>;
  return (
    <table className={tblCls}>
      <thead>
        <tr>
          <th>Date</th><th>Merchant</th><th>Account</th>
          <th className="text-right">Amount</th><th>Category</th><th></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((t: any) => (
          <tr key={t.id}>
            <td className="whitespace-nowrap tabular-nums text-slate-600">{t.date}</td>
            <td>
              <span className="font-medium">{t.merchant}</span>
              {t.note && <span className="text-slate-400"> · {t.note}</span>}
            </td>
            <td className="text-slate-500">{acctName(t.account_id)}</td>
            <td className="text-right"><Amt cents={t.amount_cents} /></td>
            <td>
              <select value={t.category_id ?? ""} title={`source: ${t.category_source || "?"}`}
                onChange={(e) => onRecat(t.id, e.target.value ? Number(e.target.value) : null)}
                className="rounded-md border border-slate-300 bg-white px-1.5 py-1 text-xs outline-none focus:border-pine-600">
                <option value="">—</option>
                {(categories?.items || []).map((c: any) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </td>
            <td className="text-right">
              <button onClick={() => onDelete(t.id)} className={btnSmCls}>Delete</button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Transfers({ tick, bump }: any) {
  const data = useGet(`/api/transfers/suggestions?tick=${tick}`);
  const [msg, setMsg] = useState("");
  const items = Array.isArray(data) ? data : [];
  async function link(s: any) {
    try {
      await api(`/api/transfers/link?out_id=${s.out_id}&in_id=${s.in_id}&transfer_id=t${Date.now()}`,
        { method: "POST" });
      setMsg("Linked.");
      bump();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  if (items.length === 0) return null;
  return (
    <Card title={`Transfer suggestions (${items.length})`}>
      {msg && <p className="mb-2 text-sm text-slate-600">{msg}</p>}
      <ul className="divide-y divide-slate-100 text-sm">
        {items.map((s: any) => (
          <li key={`${s.out_id}-${s.in_id}`} className="flex items-center justify-between py-1">
            <span>#{s.out_id} ↔ #{s.in_id} · {dollars(s.amount_cents)} · {s.date}</span>
            <button onClick={() => link(s)} className={btnSmCls}>Link</button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function Transactions() {
  const [f, setF] = useState({ q: "", account_id: "", category_id: "", date_from: "", date_to: "", offset: 0 });
  const [tick, setTick] = useState(0);
  const bump = () => setTick((t) => t + 1);
  const qs = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(f.offset), tick: String(tick) });
  for (const k of ["q", "account_id", "category_id", "date_from", "date_to"]) {
    if ((f as any)[k]) qs.set(k, (f as any)[k]);
  }
  const data = useGet(`/api/transactions?${qs}`);
  const accounts = useGet("/api/accounts?limit=500");
  const categories = useGet("/api/categories?limit=500");
  const acctById = Object.fromEntries(((accounts as any)?.items || []).map((a: any) => [a.id, a.name]));

  async function recat(id: number, category_id: number | null) {
    await api(`/api/transactions/${id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category_id }),
    });
    bump();
  }
  async function del(id: number) {
    if (!window.confirm(`Delete transaction #${id}?`)) return;
    await api(`/api/transactions/${id}`, { method: "DELETE" });
    bump();
  }

  const total = data?.total || 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.floor(f.offset / PAGE_SIZE);
  return (
    <Page title="Transactions">
      <Transfers tick={tick} bump={bump} />
      <Card title={`All transactions (${total})`}>
        <Error data={data} />
        <Filters f={f} set={setF} accounts={accounts} categories={categories} />
        <TxnTable data={data} acctName={(id: number) => acctById[id] || `#${id}`}
          categories={categories} onRecat={recat} onDelete={del} />
        <div className="mt-3 flex items-center gap-2 text-sm">
          <button disabled={page <= 0} onClick={() => setF({ ...f, offset: f.offset - PAGE_SIZE })}
            className={btnSmCls}>← Prev</button>
          <span className="text-slate-500">Page {page + 1} of {pages}</span>
          <button disabled={page + 1 >= pages} onClick={() => setF({ ...f, offset: f.offset + PAGE_SIZE })}
            className={btnSmCls}>Next →</button>
        </div>
      </Card>
    </Page>
  );
}
