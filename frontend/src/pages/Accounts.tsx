import { useState } from "react";
import { api } from "../main";
import { Amt, btnCls, Card, dollars, Empty, Error, inputCls, Page, tblCls, useGet } from "./_shared";

const TYPES = [
  "checking", "savings", "credit", "brokerage", "401k",
  "Roth", "Traditional IRA", "HSA", "529", "other"
];

function AddAccount({ onDone }: any) {
  const [name, setName] = useState("");
  const [type, setType] = useState("checking");
  const [balance, setBalance] = useState("0");
  const [msg, setMsg] = useState("");
  async function submit(e: any) {
    e.preventDefault();
    if (!name.trim()) { setMsg("Name is required."); return; }
    try {
      await api("/api/accounts", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(), type,
          balance_cents: Math.round(Number(balance || 0) * 100),
        }),
      });
      setName(""); setBalance("0"); setMsg("");
      onDone();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
      <label className="text-sm">Name
        <input value={name} onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Schwab Brokerage" className={`${inputCls} ml-1 w-52`} />
      </label>
      <label className="text-sm">Type
        <select value={type} onChange={(e) => setType(e.target.value)} className={`${inputCls} ml-1`}>
          {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </label>
      <label className="text-sm">Balance $
        <input value={balance} onChange={(e) => setBalance(e.target.value)} inputMode="decimal"
          className={`${inputCls} ml-1 w-28`} />
      </label>
      <button className={btnCls}>Add account</button>
      {msg && <span className="text-sm text-slate-600">{msg}</span>}
    </form>
  );
}

export default function Accounts() {
  const [tick, setTick] = useState(0);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");
  const [msg, setMsg] = useState("");
  const data = useGet(`/api/accounts?limit=500&tick=${tick}`);
  const items = data?.items || [];
  const total = items.reduce((s: number, a: any) => s + Number(a.balance_cents || 0), 0);
  async function saveName(id: number) {
    if (!editingName.trim()) { setMsg("Name is required."); return; }
    try {
      await api(`/api/accounts/${id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editingName.trim() }),
      });
      setEditingId(null); setEditingName(""); setMsg("");
      setTick((t) => t + 1);
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  return (
    <Page title="Accounts">
      <Card title="Add account">
        <AddAccount onDone={() => setTick((t) => t + 1)} />
      </Card>
      <Card title={`All accounts (${items.length}) · total ${dollars(total)}`}>
        <Error data={data} />
        {items.length === 0 ? (
          <Empty>No accounts yet — add one above or import a CSV.</Empty>
        ) : (
          <table className={tblCls}>
            <thead>
              <tr>
                <th>Name</th><th>Type</th><th className="text-right">Balance</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a: any) => (
                <tr key={a.id}>
                  <td className="font-medium">
                    {editingId === a.id ? (
                      <form onSubmit={(e) => { e.preventDefault(); saveName(a.id); }} className="flex gap-1">
                        <input autoFocus value={editingName} onChange={(e) => setEditingName(e.target.value)}
                          className={`${inputCls} w-48 py-1`} />
                        <button className={btnCls}>Save</button>
                      </form>
                    ) : (
                      <button onClick={() => { setEditingId(a.id); setEditingName(a.name); setMsg(""); }}
                        className="text-left hover:text-pine-700 hover:underline">{a.name}</button>
                    )}
                  </td>
                  <td className="text-slate-500">{a.type}</td>
                  <td className="text-right"><Amt cents={a.balance_cents} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {msg && <p className="mt-3 text-sm text-slate-600">{msg}</p>}
      </Card>
    </Page>
  );
}
