import { useState } from "react";
import { api } from "../main";
import { Amt, btnCls, btnSmCls, Card, dollars, Empty, Error, inputCls, Page, Stat, tblCls, useGet } from "./_shared";

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
        className="text-sm text-slate-500 file:mr-2 file:rounded-lg file:border-0 file:bg-pine-800 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-pine-700" />
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
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="Market value">{dollars(summary?.market_cents)}</Stat>
        <Stat label="Cost basis">{dollars(summary?.cost_cents)}</Stat>
        <Stat label="Gain / loss"><Amt cents={summary?.gain_cents} /></Stat>
      </div>
      <Card title={`Positions (${positions.length})`}>
        <Error data={summary} />
        {positions.length === 0 ? (
          <Empty>No positions yet — add a holding below.</Empty>
        ) : (
          <table className={tblCls}>
            <thead>
              <tr>
                <th>Symbol</th><th className="text-right">Shares</th>
                <th className="text-right">Price</th><th className="text-right">Market</th>
                <th className="text-right">Cost</th><th className="text-right">Gain</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p: any) => (
                <tr key={p.symbol}>
                  <td className="font-medium">{p.symbol}</td>
                  <td className="text-right tabular-nums">{shares(p.quantity_milli)}</td>
                  <td className="text-right tabular-nums">{dollars(p.price_cents)}</td>
                  <td className="text-right tabular-nums">{dollars(p.market_cents)}</td>
                  <td className="text-right"><Amt cents={p.cost_cents} /></td>
                  <td className="text-right"><Amt cents={p.gain_cents} /></td>
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
          <table className={`${tblCls} mt-3`}>
            <thead>
              <tr>
                <th>Symbol</th><th className="text-right">Shares</th>
                <th className="text-right">Cost</th><th>Acquired</th><th></th>
              </tr>
            </thead>
            <tbody>
              {lotItems.map((l: any) => (
                <tr key={l.id}>
                  <td className="font-medium">{l.symbol}</td>
                  <td className="text-right tabular-nums">{shares(l.quantity_milli)}</td>
                  <td className="text-right"><Amt cents={l.cost_cents} /></td>
                  <td className="tabular-nums text-slate-500">{l.acquired || "—"}</td>
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
