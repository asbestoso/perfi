import { useState } from "react";
import { api } from "../main";
import { Amt, btnCls, Card, Empty, Error, inputCls, Page, tblCls, today, useGet } from "./_shared";

const CADENCES = ["weekly", "biweekly", "monthly", "quarterly", "yearly"];

function AddRecurring({ onDone }: any) {
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [cadence, setCadence] = useState("monthly");
  const [nextDue, setNextDue] = useState(today());
  const [msg, setMsg] = useState("");
  async function submit(e: any) {
    e.preventDefault();
    if (!name.trim()) { setMsg("Name is required."); return; }
    try {
      await api("/api/recurring", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(), amount_cents: Math.round(Number(amount || 0) * 100),
          cadence, next_due: nextDue,
        }),
      });
      setName(""); setAmount(""); setMsg("");
      onDone();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
      <label className="text-sm">Name
        <input value={name} onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Netflix" className={`${inputCls} ml-1 w-44`} />
      </label>
      <label className="text-sm">Amount $
        <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal"
          placeholder="15.99" className={`${inputCls} ml-1 w-24`} />
      </label>
      <label className="text-sm">Cadence
        <select value={cadence} onChange={(e) => setCadence(e.target.value)} className={`${inputCls} ml-1`}>
          {CADENCES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
      <label className="text-sm">Next due
        <input type="date" value={nextDue} onChange={(e) => setNextDue(e.target.value)}
          className={`${inputCls} ml-1`} />
      </label>
      <button className={btnCls}>Add</button>
      {msg && <span className="text-sm text-slate-600">{msg}</span>}
    </form>
  );
}

export default function Recurring() {
  const [tick, setTick] = useState(0);
  const [msg, setMsg] = useState("");
  const bump = () => setTick((t) => t + 1);
  const data = useGet(`/api/recurring?limit=500&tick=${tick}`);
  const items = data?.items || [];

  async function detect() {
    setMsg("Detecting…");
    try {
      const r = await api("/api/recurring/detect", { method: "POST" });
      setMsg(`Detected: ${r.created.length} new, ${r.updated.length} updated.`);
      bump();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }

  return (
    <Page title="Recurring">
      <Card title="Detect from history">
        <div className="flex items-center gap-2">
          <button onClick={detect} className={btnCls}>Run detection</button>
          {msg && <span className="text-sm text-slate-600">{msg}</span>}
        </div>
        <p className="mt-2 text-sm text-slate-500">
          Finds repeat merchant + amount charges at regular intervals and saves them here.
        </p>
      </Card>
      <Card title="Add recurring">
        <AddRecurring onDone={bump} />
      </Card>
      <Card title={`All recurring (${items.length})`}>
        <Error data={data} />
        {items.length === 0 ? (
          <Empty>None yet — run detection or add one above.</Empty>
        ) : (
          <table className={tblCls}>
            <thead>
              <tr>
                <th>Name</th><th className="text-right">Amount</th>
                <th>Cadence</th><th>Next due</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r: any) => (
                <tr key={r.id}>
                  <td className="font-medium">{r.name}</td>
                  <td className="text-right"><Amt cents={r.amount_cents} /></td>
                  <td className="text-slate-500">{r.cadence}</td>
                  <td className="tabular-nums">{r.next_due}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </Page>
  );
}
