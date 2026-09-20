import { Fragment, useEffect, useState } from "react";
import { api } from "../main";
import { btnCls, Card, dollars, Empty, Error, inputCls, Page, Stat, tblCls, today, useGet } from "./_shared";

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

function AddHolding({ onDone, accounts, holdings }: any) {
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
    const normalized = symbol.trim().toUpperCase();
    const existing = (holdings?.holdings || []).find(
      (holding: any) => holding.symbol.toUpperCase() === normalized
        && String(holding.account_id) === accountId
    );
    if (existing && !window.confirm(
      `${normalized} already exists in this account. Replace its share quantity?`
    )) return;
    try {
      await api("/api/investments", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: normalized,
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

function AddOrder({ onDone, accounts }: any) {
  const [symbol, setSymbol] = useState("");
  const [accountId, setAccountId] = useState(
    () => localStorage.getItem("perfi.lastHoldingAccountId") || ""
  );
  const [side, setSide] = useState("buy");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [fees, setFees] = useState("0");
  const [executedAt, setExecutedAt] = useState(today());
  const [linkedTxn, setLinkedTxn] = useState("");
  const [msg, setMsg] = useState("");
  async function submit(e: any) {
    e.preventDefault();
    if (!symbol.trim() || !accountId || !qty || !price || !executedAt) {
      setMsg("Symbol, account, quantity, price, and date are required."); return;
    }
    try {
      await api("/api/investment-orders", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: symbol.trim().toUpperCase(), account_id: Number(accountId), side,
          quantity_milli: Math.round(Number(qty) * 1000),
          price_cents: Math.round(Number(price) * 100),
          fees_cents: Math.round(Number(fees || 0) * 100),
          executed_at: executedAt,
          ...(linkedTxn ? { linked_transaction_id: Number(linkedTxn) } : {}),
        }),
      });
      setSymbol(""); setQty(""); setPrice(""); setFees("0"); setLinkedTxn(""); setMsg("");
      onDone();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-4 rounded-lg bg-slate-50 p-4">
      <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Symbol
        <input value={symbol} onChange={(e) => setSymbol(e.target.value)}
          placeholder="VTI" className={`${inputCls} w-24`} />
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Action
        <select value={side} onChange={(e) => setSide(e.target.value)} className={inputCls}>
          <option value="buy">Buy</option><option value="sell">Sell</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Shares
        <input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal"
          placeholder="10" className={`${inputCls} w-24`} />
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Price
        <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal"
          placeholder="100.00" className={`${inputCls} w-28`} />
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Fees
        <input value={fees} onChange={(e) => setFees(e.target.value)} inputMode="decimal"
          className={`${inputCls} w-24`} />
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Date
        <input type="date" value={executedAt} onChange={(e) => setExecutedAt(e.target.value)}
          className={inputCls} />
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">Cash txn #
        <input value={linkedTxn} onChange={(e) => setLinkedTxn(e.target.value)} inputMode="numeric"
          placeholder="optional" title="Link the cash leg (e.g. the checking transfer). It leaves spending totals."
          className={`${inputCls} w-24`} />
      </label>
      <label className="flex min-w-52 flex-1 flex-col gap-1 text-xs font-medium text-slate-600">Account
        <select value={accountId} onChange={(e) => {
          setAccountId(e.target.value);
          localStorage.setItem("perfi.lastHoldingAccountId", e.target.value);
        }} className={inputCls} required>
          <option value="">Select account</option>
          {(accounts?.items || []).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </label>
      <button className={btnCls}>Add order</button>
      {msg && <span className="basis-full text-sm text-slate-600">{msg}</span>}
    </form>
  );
}

export default function Investments() {
  const [tick, setTick] = useState(0);
  const [expandedSymbol, setExpandedSymbol] = useState("");
  const [holdingNames, setHoldingNames] = useState<Record<string, string>>({});
  const bump = () => setTick((t) => t + 1);
  const { summary, refreshing } = useInvestmentSummary(tick);
  const accounts = useGet("/api/accounts?limit=500");
  const holdings = useGet("/api/investments");
  const positions = summary?.positions || [];

  async function loadHoldingName(symbol: string, currentName?: string) {
    if (currentName || holdingNames[symbol]) return;
    try {
      const result = await api(`/api/investments/name/${encodeURIComponent(symbol)}`);
      if (result.name) setHoldingNames((current) => ({ ...current, [symbol]: result.name }));
    } catch {
      // Hover metadata is optional; the symbol remains visible without it.
    }
  }

  return (
    <Page title="Investments">
      <Card title="Add order" hint="Orders record buys and sells and move holdings. Fees default to $0.00 and date defaults to today. Link the cash txn # to keep its leg out of spending.">
        <AddOrder onDone={bump} accounts={accounts} />
      </Card>
      <Card title="Add holding">
        <AddHolding onDone={bump} accounts={accounts} holdings={holdings} />
      </Card>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-1">
        <Stat label="Market value">{dollars(summary?.market_cents)}</Stat>
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
                    <span
                      title={p.name || holdingNames[p.symbol] || p.symbol}
                      onMouseEnter={() => loadHoldingName(p.symbol, p.name)}
                    >{p.symbol}</span>
                  </td>
                  <td className="text-right tabular-nums">{shares(p.quantity_milli)}</td>
                  <td className="text-right tabular-nums">{dollars(p.price_cents)}</td>
                  <td className="text-right tabular-nums">{dollars(p.market_cents)}</td>
                </tr>
                {expandedSymbol === p.symbol && (
                  <tr key={`${p.symbol}-accounts`} className="bg-slate-50">
                    <td colSpan={4} className="px-4 py-3">
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
    </Page>
  );
}
