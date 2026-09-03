import { useState } from "react";
import { api } from "../main";
import { btnCls, btnSmCls, Card, dollars, Error, inputCls, Page, useGet } from "./_shared";

function shares(milli: any) {
  return (Number(milli || 0) / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function AddHolding({ onDone }: any) {
  const [symbol, setSymbol] = useState("");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [msg, setMsg] = useState("");
  async function submit(e: any) {
    e.preventDefault();
    if (!symbol.trim()) { setMsg("Symbol is required."); return; }
    try {
      await api("/api/investments", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: symbol.trim().toUpperCase(),
          quantity_milli: Math.round(Number(qty || 0) * 1000),
          price_cents: Math.round(Number(price || 0) * 100),
        }),
      });
      setSymbol(""); setQty(""); setPrice(""); setMsg("");
      onDone();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
      <label className="text-sm">Symbol
        <input value={symbol} onChange={(e) => setSymbol(e.target.value)}
          placeholder="VTI" className={`${inputCls} ml-1 w-24`} />
      </label>
      <label className="text-sm">Shares
        <input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal"
          placeholder="10" className={`${inputCls} ml-1 w-24`} />
      </label>
      <label className="text-sm">Price $
        <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal"
          placeholder="250.00" className={`${inputCls} ml-1 w-28`} />
      </label>
      <button className={btnCls}>Add holding</button>
      {msg && <span className="text-sm text-slate-600">{msg}</span>}
    </form>
  );
}

function AddLot({ onDone }: any) {
  const [symbol, setSymbol] = useState("");
  const [qty, setQty] = useState("");
  const [cost, setCost] = useState("");
  const [acquired, setAcquired] = useState("");
  const [msg, setMsg] = useState("");
  async function submit(e: any) {
    e.preventDefault();
    if (!symbol.trim()) { setMsg("Symbol is required."); return; }
    try {
      await api("/api/lots", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: symbol.trim().toUpperCase(),
          quantity_milli: Math.round(Number(qty || 0) * 1000),
          cost_cents: Math.round(Number(cost || 0) * 100),
          acquired: acquired || null,
        }),
      });
      setSymbol(""); setQty(""); setCost(""); setAcquired(""); setMsg("");
      onDone();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
      <label className="text-sm">Symbol
        <input value={symbol} onChange={(e) => setSymbol(e.target.value)}
          className={`${inputCls} ml-1 w-24`} />
      </label>
      <label className="text-sm">Shares
        <input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal"
          className={`${inputCls} ml-1 w-24`} />
      </label>
      <label className="text-sm">Cost $
        <input value={cost} onChange={(e) => setCost(e.target.value)} inputMode="decimal"
          className={`${inputCls} ml-1 w-28`} />
      </label>
      <label className="text-sm">Acquired
        <input type="date" value={acquired} onChange={(e) => setAcquired(e.target.value)}
          className={`${inputCls} ml-1`} />
      </label>
      <button className={btnCls}>Add lot</button>
      {msg && <span className="text-sm text-slate-600">{msg}</span>}
    </form>
  );
}

function LotImport({ onDone }: any) {
  const [msg, setMsg] = useState("");
  async function submit(e: any) {
    e.preventDefault();
    const file = e.target.elements.file.files[0];
    if (!file) { setMsg("Pick a file first."); return; }
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api("/api/investments/import", { method: "POST", body: fd });
      setMsg(`Imported ${r.created}, skipped ${r.skipped}.`);
      onDone();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
      <input name="file" type="file" accept=".csv"
        className="text-sm text-slate-500 file:mr-2 file:rounded-md file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-sm file:text-white hover:file:bg-slate-700" />
      <button className={btnCls}>Import lots CSV</button>
      {msg && <span className="text-sm text-slate-600">{msg}</span>}
    </form>
  );
}

export default function Investments() {
  const [tick, setTick] = useState(0);
  const bump = () => setTick((t) => t + 1);
  const summary = useGet(`/api/investments/summary?tick=${tick}`);
  const lots = useGet(`/api/lots?limit=500&tick=${tick}`);
  const positions = summary?.positions || [];
  const lotItems = lots?.items || [];

  async function delLot(id: number) {
    if (!window.confirm(`Delete lot #${id}?`)) return;
    await api(`/api/lots/${id}`, { method: "DELETE" });
    bump();
  }

  return (
    <Page title="Investments">
      <div className="grid grid-cols-3 gap-4">
        <Card title="Market value"><p className="text-xl font-semibold">{dollars(summary?.market_cents)}</p></Card>
        <Card title="Cost basis"><p className="text-xl font-semibold">{dollars(summary?.cost_cents)}</p></Card>
        <Card title="Gain / loss">
          <p className={`text-xl font-semibold ${(summary?.gain_cents || 0) < 0 ? "text-red-700" : "text-green-700"}`}>
            {dollars(summary?.gain_cents)}
          </p>
        </Card>
      </div>
      <Card title={`Positions (${positions.length})`}>
        <Error data={summary} />
        {positions.length === 0 ? (
          <p className="text-sm text-slate-500">No positions yet — add a holding below.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-slate-500">
                <th className="py-1">Symbol</th><th className="text-right">Shares</th>
                <th className="text-right">Price</th><th className="text-right">Market</th>
                <th className="text-right">Cost</th><th className="text-right">Gain</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {positions.map((p: any) => (
                <tr key={p.symbol}>
                  <td className="py-1 font-medium">{p.symbol}</td>
                  <td className="text-right">{shares(p.quantity_milli)}</td>
                  <td className="text-right">{dollars(p.price_cents)}</td>
                  <td className="text-right">{dollars(p.market_cents)}</td>
                  <td className="text-right">{p.cost_cents == null ? "—" : dollars(p.cost_cents)}</td>
                  <td className={`text-right ${p.gain_cents == null ? "" : p.gain_cents < 0 ? "text-red-700" : "text-green-700"}`}>
                    {p.gain_cents == null ? "—" : dollars(p.gain_cents)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Card title="Add holding">
        <AddHolding onDone={bump} />
      </Card>
      <Card title={`Tax lots (${lotItems.length})`}>
        <Error data={lots} />
        <AddLot onDone={bump} />
        <div className="mt-3"><LotImport onDone={bump} /></div>
        {lotItems.length > 0 && (
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-slate-500">
                <th className="py-1">Symbol</th><th className="text-right">Shares</th>
                <th className="text-right">Cost</th><th>Acquired</th><th></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {lotItems.map((l: any) => (
                <tr key={l.id}>
                  <td className="py-1">{l.symbol}</td>
                  <td className="text-right">{shares(l.quantity_milli)}</td>
                  <td className="text-right">{dollars(l.cost_cents)}</td>
                  <td className="text-slate-500">{l.acquired || "—"}</td>
                  <td className="text-right">
                    <button onClick={() => delLot(l.id)} className={btnSmCls}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </Page>
  );
}
