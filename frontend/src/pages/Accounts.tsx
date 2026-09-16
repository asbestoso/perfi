import { useState } from "react";
import { api } from "../main";
import { Amt, btnCls, Card, dollars, Empty, Error, inputCls, Page, tblCls, useGet } from "./_shared";

const TYPES = [
  "checking", "savings", "credit", "brokerage", "401k",
  "Roth", "Traditional IRA", "HSA", "529", "other"
];
const DOMAINS = ["spending", "investing", "mixed"];

function AddAccount({ onDone }: any) {
  const [name, setName] = useState("");
  const [type, setType] = useState("checking");
  const [domain, setDomain] = useState("spending");
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
          domain,
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
      <label className="text-sm">Group
        <select value={domain} onChange={(e) => setDomain(e.target.value)} className={`${inputCls} ml-1`}>
          {DOMAINS.map((d) => <option key={d} value={d}>{d}</option>)}
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
  const [editing, setEditing] = useState<{ id: number; field: string } | null>(null);
  const [draft, setDraft] = useState("");
  const [msg, setMsg] = useState("");
  const data = useGet(`/api/accounts?limit=500&tick=${tick}`);
  const items = data?.items || [];
  const total = items.reduce((s: number, a: any) => s + Number(a.balance_cents || 0), 0);
  function startEdit(a: any, field: string) {
    setEditing({ id: a.id, field });
    setDraft(field === "name" ? a.name : field === "type" ? a.type : a.domain);
    setMsg("");
  }
  function isEditing(a: any, field: string) {
    return editing != null && editing.id === a.id && editing.field === field;
  }
  async function saveField(a: any, field: string, value: string) {
    const clean = field === "name" ? value.trim() : value;
    if (field === "name" && !clean) { setMsg("Name is required."); return; }
    try {
      await api(`/api/accounts/${a.id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: clean }),
      });
      setEditing(null); setMsg("");
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
                <th>Name</th><th>Type</th><th>Group</th><th className="text-right">Balance</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a: any) => (
                <tr key={a.id}>
                  <td className="font-medium">
                    {isEditing(a, "name") ? (
                      <form onSubmit={(e) => { e.preventDefault(); saveField(a, "name", draft); }} className="flex gap-1">
                        <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)}
                          className={`${inputCls} w-48 py-1`} />
                        <button className={btnCls}>Save</button>
                      </form>
                    ) : (
                      <button onClick={() => startEdit(a, "name")}
                        className="text-left hover:text-pine-700 hover:underline">{a.name}</button>
                    )}
                  </td>
                  <td className="text-slate-500">
                    {isEditing(a, "type") ? (
                      <select autoFocus value={draft}
                        onChange={(e) => saveField(a, "type", e.target.value)}
                        className={`${inputCls} py-1`}>
                        {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                    ) : (
                      <button onClick={() => startEdit(a, "type")}
                        className="text-left hover:text-pine-700 hover:underline">{a.type}</button>
                    )}
                  </td>
                  <td className="text-slate-500">
                    {isEditing(a, "domain") ? (
                      <select autoFocus value={draft}
                        onChange={(e) => saveField(a, "domain", e.target.value)}
                        className={`${inputCls} py-1`}>
                        {DOMAINS.map((d) => <option key={d} value={d}>{d}</option>)}
                      </select>
                    ) : (
                      <button onClick={() => startEdit(a, "domain")}
                        className="text-left hover:text-pine-700 hover:underline">{a.domain}</button>
                    )}
                  </td>
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
