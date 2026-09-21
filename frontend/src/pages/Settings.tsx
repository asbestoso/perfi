import { useState } from "react";
import { api } from "../main";
import { btnCls, btnDangerCls, btnSmCls, Card, Error, inputCls, Page, useGet } from "./_shared";

function Categories({ tick, bump }: any) {
  const data = useGet(`/api/categories?limit=500&tick=${tick}`);
  const items = data?.items || [];
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  const [editing, setEditing] = useState<any>(null);

  async function add(e: any) {
    e.preventDefault();
    if (!name.trim()) { setMsg("Name is required."); return; }
    try {
      await api("/api/categories", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      setName(""); setMsg(""); bump();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  async function saveEdit() {
    try {
      await api(`/api/categories/${editing.id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editing.name }),
      });
      setEditing(null); bump();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  async function del(id: number) {
    if (!window.confirm(`Delete category #${id}? Transactions keep their history but lose the label.`)) return;
    try {
      await api(`/api/categories/${id}`, { method: "DELETE" });
      bump();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }

  return (
    <Card title={`Categories (${items.length})`}>
      <form onSubmit={add} className="mb-3 flex items-end gap-2">
        <label className="text-sm">Name
          <input value={name} onChange={(e) => setName(e.target.value)} className={`${inputCls} ml-1 w-44`} />
        </label>
        <button className={btnCls}>Add</button>
        {msg && <span className="text-sm text-slate-600">{msg}</span>}
      </form>
      <Error data={data} />
      <ul className="divide-y divide-slate-100 text-sm">
        {items.map((c: any) => (
          <li key={c.id} className="flex items-center justify-between py-1">
            {editing?.id === c.id ? (
              <span className="flex items-center gap-2">
                <input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                  className={inputCls} />
                <button onClick={saveEdit} className={btnSmCls}>Save</button>
                <button onClick={() => setEditing(null)} className={btnSmCls}>Cancel</button>
              </span>
            ) : (
              <span>{c.name}{c.parent && <span className="text-slate-400"> · {c.parent}</span>}</span>
            )}
            {editing?.id !== c.id && (
              <span className="space-x-1">
                <button onClick={() => setEditing({ id: c.id, name: c.name })} className={btnSmCls}>Rename</button>
                <button onClick={() => del(c.id)} className={btnSmCls}>Delete</button>
              </span>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Rules({ tick, bump, categories }: any) {
  const data = useGet(`/api/rules?tick=${tick}`);
  const items = Array.isArray(data) ? data : [];
  const catById = Object.fromEntries(((categories as any)?.items || []).map((c: any) => [c.id, c.name]));
  const [pattern, setPattern] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [msg, setMsg] = useState("");

  async function add(e: any) {
    e.preventDefault();
    if (!pattern.trim() || !categoryId) { setMsg("Pattern and category are required."); return; }
    try {
      await api("/api/rules", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pattern: pattern.trim(), category_id: Number(categoryId) }),
      });
      setPattern(""); setCategoryId(""); setMsg(""); bump();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  async function del(id: number) {
    await api(`/api/rules/${id}`, { method: "DELETE" });
    bump();
  }

  return (
    <Card title={`Categorization rules (${items.length})`}>
      <form onSubmit={add} className="mb-3 flex flex-wrap items-end gap-2">
        <label className="text-sm">Pattern (regex)
          <input value={pattern} onChange={(e) => setPattern(e.target.value)}
            placeholder="netflix.*" className={`${inputCls} ml-1 w-44`} />
        </label>
        <label className="text-sm">Category
          <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className={`${inputCls} ml-1`}>
            <option value="">—</option>
            {(categories?.items || []).map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <button className={btnCls}>Add rule</button>
        {msg && <span className="text-sm text-slate-600">{msg}</span>}
      </form>
      <Error data={data} />
      {items.length === 0 ? (
        <p className="text-sm text-slate-500">No rules — unmatched transactions stay Uncategorized.</p>
      ) : (
        <ul className="divide-y divide-slate-100 text-sm">
          {items.map((r: any) => (
            <li key={r.id} className="flex items-center justify-between py-1">
              <span><code className="rounded bg-slate-100 px-1">{r.pattern}</code> → {catById[r.category_id] || `#${r.category_id}`}</span>
              <button onClick={() => del(r.id)} className={btnSmCls}>Delete</button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Export() {
  const [msg, setMsg] = useState("");
  async function download() {
    try {
      const r = await fetch("/api/export/transactions");
      if (!r.ok) throw new Error(`/api/export/transactions: ${r.status}`);
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "transactions.csv";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  return (
    <Card title="Export">
      <div className="flex items-center gap-2">
        <button onClick={download} className={btnCls}>Download transactions CSV</button>
        {msg && <span className="text-sm text-slate-600">{msg}</span>}
      </div>
    </Card>
  );
}

function DangerZone({ bump }: any) {
  const [msg, setMsg] = useState("");
  async function clear() {
    if (!window.confirm("Delete ALL data (transactions, imports, accounts, categories)? Settings are kept. This cannot be undone.")) return;
    try {
      const r = await api("/api/admin/clear", { method: "POST" });
      const total = Object.values(r.deleted || {}).reduce((a: number, b: any) => a + Number(b), 0);
      setMsg(`Cleared ${total} rows. Defaults reseeded.`);
      bump();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  return (
    <Card title="Danger zone">
      <div className="flex items-center gap-2">
        <button onClick={clear} className={btnDangerCls}>
          Clear all data
        </button>
        {msg && <span className="text-sm text-slate-600">{msg}</span>}
      </div>
    </Card>
  );
}

export default function Settings() {
  const [tick, setTick] = useState(0);
  const bump = () => setTick((t) => t + 1);
  const categories = useGet(`/api/categories?limit=500&tick=${tick}`);
  return (
    <Page title="Settings">
      <Categories tick={tick} bump={bump} />
      <Rules tick={tick} bump={bump} categories={categories} />
      <Export />
      <DangerZone bump={bump} />
    </Page>
  );
}
