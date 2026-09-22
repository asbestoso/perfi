import React, { Fragment, useEffect, useMemo, useState } from "react";
import { api } from "../main";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { btnCls, Card, dollars, Empty, Error, inputCls, Page, Stat, tblCls, thousands, today, useGet, useSortable } from "./_shared";

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

const categories = ["US", "Intl", "Bonds", "Alts", "Cash"];
const categoryColors = ["#166534", "#2563eb", "#b45309", "#7c3aed", "#0891b2", "#64748b"];
const targetAllocations: Record<string, number> = {
  US: 55, Intl: 30, Alts: 1, Bonds: 14, Cash: 0,
};

export default function Investments() {
  const [tick, setTick] = useState(0);
  const [expandedSymbol, setExpandedSymbol] = useState("");
  const [holdingNames, setHoldingNames] = useState<Record<string, string>>({});
  const [editingHolding, setEditingHolding] = useState<number | null>(null);
  const [editQty, setEditQty] = useState("");
  const [editMsg, setEditMsg] = useState("");
  const [filter, setFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [accountFilter, setAccountFilter] = useState("");
  const [message, setMessage] = useState("");
  const [categoryBySymbol, setCategoryBySymbol] = useState<Record<string, string>>({});
  const [allocationSymbol, setAllocationSymbol] = useState("");
  const [allocationDraft, setAllocationDraft] = useState<Record<string, string>>({});
  const bump = () => setTick((t) => t + 1);
  const { summary, refreshing } = useInvestmentSummary(tick);
  const accounts = useGet("/api/accounts?limit=500");
  const holdings = useGet("/api/investments");
  const positions = useMemo(() => (summary?.positions || []).map((position: any) => {
    const overlay = Object.prototype.hasOwnProperty.call(categoryBySymbol, position.symbol.toUpperCase())
      ? categoryBySymbol[position.symbol.toUpperCase()]
      : undefined;
    return {
      ...position,
      category: overlay !== undefined
        ? overlay
        : position.allocations && Object.keys(position.allocations).length > 1
          ? "Mixed" : position.category,
      allocations: overlay !== undefined && overlay !== "Mixed" ? {} : position.allocations,
    };
  }), [summary, categoryBySymbol]);
  const positionsTable = useSortable("symbol", {
    symbol: (p: any) => p.symbol,
    account_name: (p: any) => `${p.accounts?.length || 0}`,
    shares: (p: any) => Number(p.quantity_milli || 0),
    price: (p: any) => Number(p.price_cents || 0),
    market: (p: any) => Number(p.market_cents || 0),
    category: (p: any) => String(p.category || "").toLowerCase(),
  });
  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const filtered = positions
      .filter((p: any) => (!needle
        || p.symbol.toLowerCase().includes(needle)
        || (p.accounts || []).some((a: any) => String(a.name || "").toLowerCase().includes(needle))))
      .filter((p: any) => !categoryFilter || p.category === categoryFilter)
      .map((p: any) => {
        const kept = accountFilter
          ? (p.accounts || []).filter((a: any) => String(a.account_id) === accountFilter)
          : (p.accounts || []);
        const accountName = accountFilter && kept.length
          ? kept[0].name
          : `${kept.length || 0} account${kept.length === 1 ? "" : "s"}`;
        const single = kept.length === 1 ? kept[0] : null;
        return {
          ...p,
          accounts: kept,
          account_name: accountName,
          quantity_milli: single ? single.quantity_milli : p.quantity_milli,
          price_cents: single ? (single.price_cents ?? p.price_cents) : p.price_cents,
          market_cents: single ? (single.market_cents ?? p.market_cents) : p.market_cents,
        };
      })
      .filter((p: any) => !accountFilter || p.accounts.length > 0);
    return positionsTable.sorted(filtered);
  }, [positions, filter, categoryFilter, accountFilter, positionsTable.sortKey, positionsTable.ascending]);

  function cancelHoldingEdit() {
    setEditingHolding(null);
    setEditQty("");
    setEditMsg("");
  }

  function startHoldingEdit(account: any) {
    setEditingHolding(account.holding_id);
    setEditQty(String(Number(account.quantity_milli || 0) / 1000));
    setEditMsg("");
  }

  function holdingQtyEditor(account: any, compact = false) {
    if (editingHolding !== account.holding_id) {
      return (
        <button type="button" title="Edit shares (0 removes)"
          onClick={() => startHoldingEdit(account)}
          className="shrink-0 tabular-nums text-slate-600 hover:text-pine-700 hover:underline">
          {shares(account.quantity_milli)}{compact ? "" : " shares"}
        </button>
      );
    }
    return (
      <span className="flex items-center justify-end gap-1">
        <input value={editQty}
          onChange={(e) => setEditQty(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") saveHoldingQty(account.holding_id);
            if (e.key === "Escape") cancelHoldingEdit();
          }}
          onBlur={cancelHoldingEdit}
          inputMode="decimal" placeholder="shares"
          className={`${inputCls} w-24 py-1`} autoFocus />
        <button type="button" onMouseDown={(e) => e.preventDefault()}
          onClick={() => saveHoldingQty(account.holding_id)}
          className={btnCls}>Save</button>
      </span>
    );
  }

  async function saveHoldingQty(holdingId: number) {    const qty = Number(editQty);
    if (!Number.isFinite(qty) || qty < 0) { setEditMsg("Shares must be 0 or more."); return; }
    if (qty === 0 && !window.confirm("Remove this holding from the account?")) return;
    try {
      await api(`/api/investments/${holdingId}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quantity_milli: Math.round(qty * 1000) }),
      });
      setEditingHolding(null);
      setEditQty("");
      setEditMsg("");
      bump();
    } catch (e: any) { setEditMsg(`Failed: ${e.message}`); }
  }

  async function loadHoldingName(symbol: string, currentName?: string) {
    if (currentName || holdingNames[symbol]) return;
    try {
      const result = await api(`/api/investments/name/${encodeURIComponent(symbol)}`);
      if (result.name) setHoldingNames((current) => ({ ...current, [symbol]: result.name }));
    } catch {
      // Hover metadata is optional; the symbol remains visible without it.
    }
  }

  async function categorize(symbol: string, category: string) {
    setMessage("");
    try {
      await api(`/api/investments/classification/${encodeURIComponent(symbol)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category: category || null }),
      });
      setCategoryBySymbol((current) => ({
        ...current,
        [symbol.toUpperCase()]: category,
      }));
    } catch (e: any) {
      setMessage(`Failed: ${e.message}`);
    }
  }

  function startAllocation(symbol: string, allocations: Record<string, number>) {
    setAllocationSymbol(symbol);
    setAllocationDraft(Object.fromEntries(categories.map((category) =>
      [category, String(allocations?.[category] || "")])));
  }

  async function saveAllocation() {
    try {
      const allocations = Object.fromEntries(categories.map((category) =>
        [category, allocationDraft[category] === "" ? 0 : Number(allocationDraft[category] || 0)]));
      await api(`/api/investments/allocation/${encodeURIComponent(allocationSymbol)}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ allocations }),
      });
      setCategoryBySymbol((current) => ({ ...current, [allocationSymbol]: "Mixed" }));
      setAllocationSymbol("");
      setMessage("");
    } catch (e: any) { setMessage(`Failed: ${e.message}`); }
  }

  const categoryBreakdown = useMemo(() => {
    const totals: Record<string, number> = {};
    positions.forEach((position: any) => {
      const value = Number(position.market_cents || 0);
      const allocations = position.allocations;
      if (allocations && Object.keys(allocations).length) {
        Object.entries(allocations).forEach(([category, percent]) => {
          totals[category] = (totals[category] || 0) + value * Number(percent) / 100;
        });
      } else {
        const category = position.category || "Uncategorized";
        totals[category] = (totals[category] || 0) + value;
      }
    });
    return Object.entries(totals)
      .filter(([, value]) => value > 0)
      .map(([name, value]) => ({ name, value }));
  }, [positions]);

  const categoryComparison = useMemo(() => {
    const total = categoryBreakdown.reduce((sum, entry) => sum + entry.value, 0);
    const actual = Object.fromEntries(categoryBreakdown.map((entry) => [
      entry.name, {
        percent: total ? (entry.value / total) * 100 : 0,
        value: entry.value,
      },
    ]));
    return [...categories, "Uncategorized"].map((category) => ({
      category,
      actual: actual[category]?.percent || 0,
      actualValue: actual[category]?.value || 0,
      target: targetAllocations[category] || 0,
      targetValue: total * (targetAllocations[category] || 0) / 100,
    }));
  }, [categoryBreakdown]);

  const tableTotals = rows.reduce((totals: { shares: number; market: number }, position: any) => ({
    shares: totals.shares + Number(position.quantity_milli || 0),
    market: totals.market + Number(position.market_cents || 0),
  }), { shares: 0, market: 0 });

  return (
    <Page title="Investments">
      <Card title="Add holding">
        <AddHolding onDone={bump} accounts={accounts} holdings={holdings} />
      </Card>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-1">
        <Stat label="Market value">{dollars(summary?.market_cents)}</Stat>
      </div>
      <Card title="Allocation by category"
        hint="Actual allocation compared with your target: 55% US, 30% Intl, 14% Bonds, and 1% Alts.">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(22rem,1fr)]">
          {categoryBreakdown.length === 0 ? (
            <Empty>No categorized holdings to chart yet.</Empty>
          ) : (
            <div className="rounded-xl bg-slate-50/80 px-2 py-3">
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie data={categoryBreakdown} dataKey="value" nameKey="name"
                    cx="50%" cy="48%" outerRadius={100} innerRadius={54}
                    paddingAngle={2} label={({ name, percent }) =>
                      `${name} ${(percent * 100).toFixed(0)}%`}>
                    {categoryBreakdown.map((entry, index) => (
                      <Cell key={entry.name} fill={categoryColors[index % categoryColors.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => dollars(value)} />
                  <Legend iconType="circle" />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="mb-3">
              <h3 className="text-sm font-semibold text-slate-800">Portfolio mix</h3>
              <p className="text-xs text-slate-500">Actual allocation versus target</p>
            </div>
            <div className="grid grid-cols-[minmax(0,1fr)_5.5rem_5.5rem_5.5rem] gap-x-4 border-b border-slate-200 pb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              <span>Category</span><span className="text-right">Actual</span><span className="text-right">Target</span><span className="text-right">Delta</span>
            </div>
            {categoryComparison.map(({ category, actual, actualValue, target, targetValue }) => (
              <div key={category} className="grid grid-cols-[minmax(0,1fr)_5.5rem_5.5rem_5.5rem] items-center gap-x-4 border-b border-slate-100 py-3 text-sm last:border-0">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 shrink-0 rounded-full"
                      style={{ backgroundColor: categoryColors[categories.indexOf(category)] || "#94a3b8" }} />
                    <span className="truncate">{category}</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-pine-600" style={{ width: `${Math.min(actual, 100)}%` }} />
                  </div>
                </div>
                <span className="text-right">
                  <span className="block font-medium tabular-nums">{actual.toFixed(1)}%</span>
                  <span className={`block text-xs tabular-nums font-semibold ${actual - target >= 0 ? "text-pine-700" : "text-red-600"}`}>{thousands(actualValue)}</span>
                </span>
                <span className="text-right">
                  <span className="block tabular-nums text-slate-500">{target.toFixed(0)}%</span>
                  <span className="block text-xs tabular-nums text-slate-400">{thousands(targetValue)}</span>
                </span>
                <span className={`text-right text-xs font-semibold tabular-nums ${actualValue - targetValue >= 0 ? "text-pine-700" : "text-red-600"}`}>
                  {actualValue - targetValue >= 0 ? "+" : "−"}{thousands(Math.abs(actualValue - targetValue))}
                </span>
              </div>
            ))}
          </div>
        </div>
      </Card>
      <Card title={`Positions (${rows.length})`}
        hint={refreshing ? "Updating prices..." : "Prices update automatically every hour. Click a share count to edit it; multi-account rows expand."}>
        <div className="mb-4 flex flex-wrap gap-3 rounded-xl bg-slate-50/80 p-3">
          <input value={filter} onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter symbol or account" className={`${inputCls} min-w-64 flex-1`} />
          <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}
            className={inputCls}>
            <option value="">All categories</option>
            {categories.map((category) => <option key={category}>{category}</option>)}
            <option value="Mixed">Mixed</option>
          </select>
          <select value={accountFilter} onChange={(e) => setAccountFilter(e.target.value)}
            className={inputCls}>
            <option value="">All accounts</option>
            {(accounts?.items || [])
              .filter((a: any) => a.domain === "investing")
              .map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
        <Error data={summary} />
        {rows.length === 0 ? (
          <Empty>{positions.length === 0 ? "No positions yet — add a holding above." : "No holdings match the current filters."}</Empty>
        ) : (
          <table className={tblCls}>
            <thead>
              <tr>
                {[
                  ["symbol", "Symbol", ""],
                  ["account_name", "Account", ""],
                  ["shares", "Shares", "text-right"],
                  ["price", "Price/share", "text-right"],
                  ["market", "Market value", "text-right"],
                  ["category", "Category", "text-right"],
                ].map(([key, label, align]) => (
                  <th key={key} onClick={() => positionsTable.sortBy(key)}
                    className={`cursor-pointer select-none hover:text-pine-700 ${align}`}>
                    <span className="block">{label}{positionsTable.arrow(key)}</span>
                    {key === "shares" && (
                      <span className="mt-1 block text-xs font-normal text-slate-400">
                        {shares(tableTotals.shares)}
                      </span>
                    )}
                    {key === "market" && (
                      <span className="mt-1 block text-xs font-normal text-slate-400">
                        {dollars(tableTotals.market)}
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((p: any) => {
                const expandable = (p.accounts?.length || 0) > 1;
                const expanded = expandable && expandedSymbol === p.symbol;
                return (
                <Fragment key={p.symbol}>
                <tr onClick={() => expandable && setExpandedSymbol(
                  expandedSymbol === p.symbol ? "" : p.symbol
                )} className={expandable ? "cursor-pointer hover:bg-slate-50" : undefined}>
                  <td className="font-medium">
                    <span className="mr-2 text-slate-400">{expanded ? "▾" : expandable ? "▸" : ""}</span>
                    <span
                      title={p.name || holdingNames[p.symbol] || p.symbol}
                      onMouseEnter={() => loadHoldingName(p.symbol, p.name)}
                    >{p.symbol}</span>
                  </td>
                  <td>
                    {expandable ? (
                      <span className="group relative">
                        {p.account_name}
                        <span className="pointer-events-none invisible absolute left-0 top-full z-10 mt-1 min-w-64 rounded-lg border border-slate-200 bg-white p-2 text-xs shadow-lg group-hover:visible">
                          {(p.accounts || []).map((account: any) => (
                            <span key={account.account_id ?? account.holding_id} className="grid grid-cols-[1fr_auto] gap-4 py-0.5">
                              <span>{account.name}</span>
                              <span className="text-right tabular-nums text-slate-600">
                                {shares(account.quantity_milli)} shares
                              </span>
                            </span>
                          ))}
                        </span>
                      </span>
                    ) : (
                      <span>{p.account_name}</span>
                    )}
                  </td>
                  <td className="text-right tabular-nums">
                    {p.accounts?.length === 1 ? holdingQtyEditor(p.accounts[0], true) : shares(p.quantity_milli)}
                  </td>
                  <td className="text-right tabular-nums">{dollars(p.price_cents)}</td>
                  <td className="text-right tabular-nums">{dollars(p.market_cents)}</td>
                  <td className="text-right">
                    <span onClick={(e) => e.stopPropagation()}>
                    <select value={p.category || ""}
                      onChange={(e) => e.target.value === "Mixed"
                        ? startAllocation(p.symbol, p.allocations)
                        : categorize(p.symbol, e.target.value)}
                      className={`${inputCls} py-1`}>
                      <option value="">Uncategorized</option>
                      {categories.map((category) => <option key={category}>{category}</option>)}
                      <option value="Mixed">Mixed</option>
                    </select>
                    </span>
                  </td>
                </tr>
                {expanded && (
                  <tr key={`${p.symbol}-accounts`} className="bg-slate-50" onClick={(e) => e.stopPropagation()}>
                    <td colSpan={6} className="px-4 py-3">
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Holdings by account
                      </div>
                      {p.accounts?.length ? (
                        <div className="mt-2 grid gap-2 sm:grid-cols-2">
                          {p.accounts.map((account: any) => (
                            <div key={account.account_id ?? "unassigned"}
                              className="flex items-center justify-between gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm">
                              <span className="min-w-0 flex-1 truncate">{account.name}</span>
                              {holdingQtyEditor(account)}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="mt-1 text-sm text-slate-500">No account holdings recorded.</p>
                      )}
                    </td>
                  </tr>
                )}
                {editMsg && editingHolding != null && p.accounts?.some(
                  (account: any) => account.holding_id === editingHolding) && (
                  <tr key={`${p.symbol}-edit-error`} onClick={(e) => e.stopPropagation()}>
                    <td colSpan={6} className="bg-slate-50 px-4 pb-3">
                      <p className="text-sm text-red-700">{editMsg}</p>
                    </td>
                  </tr>
                )}
                {allocationSymbol === p.symbol && (
                  <tr onClick={(e) => e.stopPropagation()}>
                    <td colSpan={6} className="bg-slate-50 px-4 py-3">
                      <div className="flex flex-wrap items-end gap-2">
                        {categories.map((category) => (
                          <label key={category} className="text-xs text-slate-600">
                            {category} %
                            <input value={allocationDraft[category] || ""}
                              onChange={(e) => setAllocationDraft((current) => ({
                                ...current, [category]: e.target.value,
                              }))}
                              className={`${inputCls} ml-1 w-20 py-1`} inputMode="decimal" />
                          </label>
                        ))}
                        <button type="button" onClick={saveAllocation} className={inputCls}>Save mix</button>
                      </div>
                    </td>
                  </tr>
                )}
                </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
        {message && <p className="mt-3 text-sm text-red-700">{message}</p>}
      </Card>
    </Page>
  );
}
