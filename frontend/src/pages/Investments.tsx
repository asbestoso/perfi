import { Fragment, useEffect, useState } from "react";
import { api } from "../main";
import { Amt, btnCls, btnSmCls, Card, dollars, Empty, Error, inputCls, Page, Stat, tblCls, useGet } from "./_shared";

function shares(milli: any) {
  return (Number(milli || 0) / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 });
}

const summaryCacheKey = "perfi.investmentSummary";

function useInvestmentSummary(tick: number) {
  const [summary, setSummary] = useState<any>(() => {
    const cached = localStorage.getItem(summaryCacheKey);
    if (!cached) return null;
    try {
      return JSON.parse(cached);
    } catch {
      localStorage.removeItem(summaryCacheKey);
      return null;
    }
  });
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let active = true;
    async function refresh() {
      setRefreshing(true);
      try {
        const next = await api(`/api/investments/summary?tick=${tick}`);
        if (!active) return;
        localStorage.setItem(summaryCacheKey, JSON.stringify(next));
        setSummary(next);
      } catch (e: any) {
        if (active) setSummary((current: any) => current
          ? { ...current, error: String(e) }
          : { error: String(e) });
      } finally {
        if (active) setRefreshing(false);
      }
    }
    refresh();
    const interval = window.setInterval(refresh, 60 * 60 * 1000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [tick]);

  return { summary, refreshing };
}

function AddHolding({ onDone, accounts }: any) {
  const [symbol, setSymbol] = useState("");
  const [accountId, setAccountId] = useState(
    () => localStorage.getItem("perfi.lastHoldingAccountId") || ""
  );
  const [qty, setQty] = useState("");
  const [msg, setMsg] = useState("");
  async function submit(e: any) {
    e.preventDefault();
    if (!symbol.trim()) { setMsg("Symbol is required."); return; }
    if (!accountId) { setMsg("Account is required."); return; }
    try {
      await api("/api/investments", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: symbol.trim().toUpperCase(),
          account_id: Number(accountId),
          quantity_milli: Math.round(Number(qty || 0) * 1000),
        }),
      });
      setSymbol(""); setQty(""); setMsg("");
      onDone();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-4 rounded-lg bg-slate-50 p-4">
      <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Symbol
        <input value={symbol} onChange={(e) => setSymbol(e.target.value)}
          placeholder="VTI" className={`${inputCls} w-24`} />
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Shares
        <input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal"
          placeholder="10" className={`${inputCls} w-24`} />
      </label>
      <label className="flex min-w-52 flex-1 flex-col gap-1 text-xs font-medium text-slate-600">Account
        <select value={accountId} onChange={(e) => {
          setAccountId(e.target.value);
          localStorage.setItem("perfi.lastHoldingAccountId", e.target.value);
        }}
          className={`${inputCls}`} required>
          <option value="">Select account</option>
          {(accounts?.items || []).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </label>
      <div className="flex flex-col gap-1">
        <span className="text-xs text-slate-500">Live price</span>
        <button className={btnCls}>Add holding</button>
      </div>
      {msg && <span className="basis-full text-sm text-slate-600">{msg}</span>}
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
  const [expandedSymbol, setExpandedSymbol] = useState("");
  const bump = () => setTick((t) => t + 1);
  const { summary, refreshing } = useInvestmentSummary(tick);
  const lots = useGet(`/api/lots?limit=500&tick=${tick}`);
  const accounts = useGet("/api/accounts?limit=500");
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
      <Card title={`Positions (${positions.length})`}
        hint={refreshing ? "Updating prices..." : "Prices update automatically every hour."}>
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
                <Fragment key={p.symbol}>
                <tr onClick={() => setExpandedSymbol(
                  expandedSymbol === p.symbol ? "" : p.symbol
                )} className="cursor-pointer hover:bg-slate-50">
                  <td className="font-medium">
                    <span className="mr-2 text-slate-400">{expandedSymbol === p.symbol ? "▾" : "▸"}</span>
                    {p.symbol}
                  </td>
                  <td className="text-right tabular-nums">{shares(p.quantity_milli)}</td>
                  <td className="text-right tabular-nums">{dollars(p.price_cents)}</td>
                  <td className="text-right tabular-nums">{dollars(p.market_cents)}</td>
                  <td className="text-right"><Amt cents={p.cost_cents} /></td>
                  <td className="text-right"><Amt cents={p.gain_cents} /></td>
                </tr>
                {expandedSymbol === p.symbol && (
                  <tr key={`${p.symbol}-accounts`} className="bg-slate-50">
                    <td colSpan={6} className="px-4 py-3">
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Holdings by account
                      </div>
                      {p.accounts?.length ? (
                        <div className="mt-2 grid gap-2 sm:grid-cols-2">
                          {p.accounts.map((account: any) => (
                            <div key={account.account_id ?? "unassigned"}
                              className="flex items-center justify-between rounded-md border border-slate-200 bg-white px-3 py-2 text-sm">
                              <span>{account.name}</span>
                              <span className="tabular-nums text-slate-600">
                                {shares(account.quantity_milli)} shares
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="mt-1 text-sm text-slate-500">No account holdings recorded.</p>
                      )}
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Card title="Add holding">
        <AddHolding onDone={bump} accounts={accounts} />
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
