import React, { useMemo, useState } from "react";
import { api } from "../main";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Badge, Card, dollars, Empty, Error, inputCls, Page, tblCls, useGet } from "./_shared";

const categories = ["US", "Intl", "Bonds", "Alts", "Cash"];
const categoryColors = ["#166534", "#2563eb", "#b45309", "#7c3aed", "#0891b2", "#64748b"];
const targetAllocations: Record<string, number> = {
  US: 55, Intl: 30, Alts: 1, Bonds: 14, Cash: 0,
};

function shareCount(milli: any) {
  return (Number(milli || 0) / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function evaluateCashExpression(expression: string) {
  const normalized = expression.replace(/\s/g, "");
  if (!normalized) return NaN;
  const tokens = normalized.match(/(\d*\.?\d+|[()+\-*/])/g);
  if (!tokens || tokens.join("") !== normalized) return NaN;
  let position = 0;
  function parseExpression(): number {
    let value = parseTerm();
    while (tokens[position] === "+" || tokens[position] === "-") {
      const operator = tokens[position++];
      const right = parseTerm();
      value = operator === "+" ? value + right : value - right;
    }
    return value;
  }
  function parseTerm(): number {
    let value = parseFactor();
    while (tokens[position] === "*" || tokens[position] === "/") {
      const operator = tokens[position++];
      const right = parseFactor();
      value = operator === "*" ? value * right : value / right;
    }
    return value;
  }
  function parseFactor(): number {
    if (tokens[position] === "+") { position++; return parseFactor(); }
    if (tokens[position] === "-") { position++; return -parseFactor(); }
    if (tokens[position] === "(") {
      position++;
      const value = parseExpression();
      if (tokens[position++] !== ")") throw new Error("Unbalanced expression");
      return value;
    }
    const value = Number(tokens[position++]);
    if (!Number.isFinite(value)) throw new Error("Invalid number");
    return value;
  }
  try {
    const result = parseExpression();
    return position === tokens.length && Number.isFinite(result) ? result : NaN;
  } catch {
    return NaN;
  }
}

export default function InvestmentAnalysis() {
  const [filter, setFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [sort, setSort] = useState("symbol");
  const [ascending, setAscending] = useState(true);
  const [message, setMessage] = useState("");
  const [categoryBySymbol, setCategoryBySymbol] = useState<Record<string, string>>({});
  const [holdingNames, setHoldingNames] = useState<Record<string, string>>({});
  const [allocationSymbol, setAllocationSymbol] = useState("");
  const [allocationDraft, setAllocationDraft] = useState<Record<string, string>>({});
  const [calculatorPercent, setCalculatorPercent] = useState("");
  const [calculatorCash, setCalculatorCash] = useState("");
  const data = useGet("/api/investments");
  const holdings = (data?.holdings || []).map((holding: any) => ({
    ...holding,
    category: Object.prototype.hasOwnProperty.call(categoryBySymbol, holding.symbol.toUpperCase())
      ? categoryBySymbol[holding.symbol.toUpperCase()]
      : holding.allocations && Object.keys(holding.allocations).length > 1
        ? "Mixed"
      : holding.category,
  }));

  async function loadHoldingName(symbol: string, currentName?: string) {
    if (currentName || holdingNames[symbol]) return;
    try {
      const result = await api(`/api/investments/name/${encodeURIComponent(symbol)}`);
      if (result.name) setHoldingNames((current) => ({ ...current, [symbol]: result.name }));
    } catch {
      // Hover metadata is optional; the symbol remains visible without it.
    }
  }

  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const filtered = holdings
      .filter((h: any) => (!needle
        || h.symbol.toLowerCase().includes(needle)
        || h.account_name.toLowerCase().includes(needle)))
      .filter((h: any) => !categoryFilter || h.category === categoryFilter);
    const displayRows = Object.values(filtered.reduce((groups: any, holding: any) => {
      const symbol = holding.symbol.toUpperCase();
      const group = groups[symbol] || {
        id: symbol, symbol, account_name: "", quantity_milli: 0,
        market_cents: 0, category: holding.category || "", allocations: holding.allocations, holdings: [],
      };
      group.quantity_milli += holding.quantity_milli;
      group.market_cents += (holding.quantity_milli * holding.price_cents) / 1000;
      group.holdings.push(holding);
      group.allocations = holding.allocations;
      group.account_name = `${group.holdings.length} account${group.holdings.length === 1 ? "" : "s"}`;
      groups[symbol] = group;
      return groups;
    }, {}));
    return displayRows
      .sort((a: any, b: any) => {
        const left = sort === "shares" ? a.quantity_milli
          : sort === "market" ? (a.market_cents ?? a.quantity_milli * a.price_cents)
          : String(a[sort] || "").toLowerCase();
        const right = sort === "shares" ? b.quantity_milli
          : sort === "market" ? (b.market_cents ?? b.quantity_milli * b.price_cents)
          : String(b[sort] || "").toLowerCase();
        const result = left < right ? -1 : left > right ? 1 : 0;
        return ascending ? result : -result;
      });
  }, [holdings, filter, categoryFilter, sort, ascending]);

  const categoryBreakdown = useMemo(() => {
    const totals: Record<string, number> = {};
    holdings.forEach((holding: any) => {
      const value = (holding.quantity_milli * holding.price_cents) / 1000;
      const allocations = holding.allocations;
      if (allocations && Object.keys(allocations).length) {
        Object.entries(allocations).forEach(([category, percent]) => {
          totals[category] = (totals[category] || 0) + value * Number(percent) / 100;
        });
      } else {
        const category = holding.category || "Uncategorized";
        totals[category] = (totals[category] || 0) + value;
      }
    });
    return Object.entries(totals)
      .filter(([, value]) => value > 0)
      .map(([name, value]) => ({ name, value }));
  }, [holdings]);

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
      total,
    }));
  }, [categoryBreakdown]);

  const portfolioTotal = categoryComparison[0]?.total || 0;
  const calculatorCashValue = evaluateCashExpression(calculatorCash);
  const calculatedCash = calculatorPercent === ""
    ? calculatorCashValue
    : String((portfolioTotal * Number(calculatorPercent || 0) / 100 / 100).toFixed(2));
  const calculatedPercent = calculatorCash === ""
    ? calculatorPercent
    : portfolioTotal && Number.isFinite(calculatorCashValue)
      ? String((calculatorCashValue / (portfolioTotal / 100) * 100).toFixed(2)) : "0.00";
  const tableTotals = rows.reduce((totals: { shares: number; market: number }, holding: any) => ({
    shares: totals.shares + Number(holding.quantity_milli || 0),
    market: totals.market + Number(
      holding.market_cents ?? (holding.quantity_milli * holding.price_cents) / 1000,
    ),
  }), { shares: 0, market: 0 });

  function sortBy(field: string) {
    if (field === sort) setAscending((value) => !value);
    else { setSort(field); setAscending(true); }
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

  return (
    <Page title="Portfolio analysis" sub="Review allocation by holding, account, and category.">
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
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-slate-800">Portfolio mix</h3>
                <p className="text-xs text-slate-500">Actual allocation versus target</p>
              </div>
              <Badge tone="slate">100% target</Badge>
            </div>
            <div className="grid grid-cols-[minmax(0,1fr)_auto_auto_minmax(6rem,auto)] gap-x-4 border-b border-slate-200 pb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              <span>Category</span><span>Actual</span><span>Target</span><span>Delta</span>
            </div>
            {categoryComparison.map(({ category, actual, actualValue, target, targetValue, total }) => (
              <div key={category} className="grid grid-cols-[minmax(0,1fr)_auto_auto_minmax(6rem,auto)] items-center gap-x-4 border-b border-slate-100 py-3 text-sm last:border-0">
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
                <span className="text-right font-medium tabular-nums">{actual.toFixed(1)}%</span>
                <span className="text-right tabular-nums text-slate-500">{target.toFixed(0)}%</span>
                <span
                  title={`Actual ${dollars(actualValue)} of ${dollars(total)} · target ${dollars(targetValue)}`}
                  className={`min-w-24 text-right text-xs font-semibold tabular-nums ${actual - target >= 0 ? "text-pine-700" : "text-amber-700"}`}>
                  <span className="block text-slate-500">{dollars(targetValue)}</span>
                  <span>{actualValue - targetValue >= 0 ? "+" : ""}{dollars(actualValue - targetValue)}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </Card>
      <Card title="Allocation calculator" hint="Convert a portfolio percentage into dollars, or dollars into a portfolio percentage.">
        <div className="rounded-xl bg-slate-50/80 p-4">
          <div className="grid gap-4 sm:grid-cols-[minmax(0,14rem)_auto_minmax(0,14rem)] sm:items-end">
            <label className="text-sm font-medium text-slate-700">
              Percentage
              <div className="relative mt-1">
                <input value={calculatorPercent}
                  onChange={(e) => { setCalculatorPercent(e.target.value); setCalculatorCash(""); }}
                  inputMode="decimal" placeholder="e.g. 14" className={`${inputCls} w-full pr-8`} />
                <span className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-slate-400">%</span>
              </div>
            </label>
            <span className="hidden pb-2 text-center text-xs font-medium uppercase tracking-wide text-slate-400 sm:block">or</span>
            <label className="text-sm font-medium text-slate-700">
              Cash value
              <div className="relative mt-1">
                <span className="pointer-events-none absolute inset-y-0 left-2 flex items-center text-slate-400">$</span>
                <input value={calculatorCash}
                  onChange={(e) => { setCalculatorCash(e.target.value); setCalculatorPercent(""); }}
                  inputMode="decimal" placeholder="e.g. 10000" className={`${inputCls} w-full pl-6`} />
              </div>
            </label>
          </div>
          <p className="mt-4 border-t border-slate-200 pt-3 text-xs text-slate-500">
            Based on a total portfolio value of <span className="font-semibold text-slate-700">{dollars(portfolioTotal)}</span>.
            {calculatorPercent !== "" && <span> {calculatorPercent}% equals <span className="font-semibold text-pine-700">{dollars(Number(calculatedCash) * 100)}</span>.</span>}
            {calculatorCash !== "" && Number.isFinite(calculatorCashValue) && <span> {dollars(calculatorCashValue * 100)} equals <span className="font-semibold text-pine-700">{calculatedPercent}%</span>.</span>}
          </p>
        </div>
      </Card>
      <Card title="Holdings" hint={filter || categoryFilter
        ? "Showing one aggregate row per symbol from the matching holdings. Click a column heading to sort."
        : "Showing one aggregate row per symbol. Click a column heading to sort."}>
        <div className="mb-4 flex flex-wrap gap-3 rounded-xl bg-slate-50/80 p-3">
          <input value={filter} onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter symbol or account" className={`${inputCls} min-w-64 flex-1`} />
          <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}
            className={inputCls}>
            <option value="">All categories</option>
            {categories.map((category) => <option key={category}>{category}</option>)}
            <option value="Mixed">Mixed</option>
          </select>
        </div>
        <Error data={data} />
        {rows.length === 0 ? <Empty>No holdings match the current filters.</Empty> : (
          <table className={tblCls}>
            <thead>
              <tr>
                {[
                  ["symbol", "Symbol"], ["account_name", "Account"],
                  ["shares", "Shares"], ["market", "Market value"],
                  ["category", "Category"],
                ].map(([field, label]) => (
                  <th key={field} onClick={() => sortBy(field)}
                    className={`select-none hover:text-pine-700 ${field === "shares" || field === "market" || field === "category" ? "text-right" : ""}`}>
                    <span className="block">{label} {sort === field && (ascending ? "↑" : "↓")}</span>
                    {field === "shares" && (
                      <span className="mt-1 block text-xs font-normal text-slate-400">
                        {shareCount(tableTotals.shares)}
                      </span>
                    )}
                    {field === "market" && (
                      <span className="mt-1 block text-xs font-normal text-slate-400">
                        {dollars(tableTotals.market)}
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((holding: any) => {
                const aggregate = Boolean(holding.holdings);
                const category = holding.allocations && Object.keys(holding.allocations).length > 1
                  ? "Mixed" : holding.category;
                const accountDetails = aggregate ? holding.holdings : [holding];
                return (
                <React.Fragment key={holding.id}>
                <tr key={holding.id}>
                  <td className="font-medium">
                    <span
                      title={holding.name || holdingNames[holding.symbol] || holding.symbol}
                      onMouseEnter={() => loadHoldingName(holding.symbol, holding.name)}
                    >{holding.symbol}</span>
                  </td>
                  <td>
                    <span className="group relative">
                      {holding.account_name}
                      <span className="pointer-events-none invisible absolute left-0 top-full z-10 mt-1 min-w-64 rounded-lg border border-slate-200 bg-white p-2 text-xs shadow-lg group-hover:visible">
                        {accountDetails.map((account: any) => (
                          <span key={account.account_id ?? account.id} className="grid grid-cols-[1fr_auto] gap-4 py-0.5">
                            <span>{account.account_name || account.name}</span>
                            <span className="text-right tabular-nums text-slate-600">
                              {shareCount(account.quantity_milli)} shares
                            </span>
                          </span>
                        ))}
                      </span>
                    </span>
                  </td>
                  <td className="text-right tabular-nums">{shareCount(holding.quantity_milli)}</td>
                  <td className="text-right tabular-nums">
                    {dollars(holding.market_cents ?? (holding.quantity_milli * holding.price_cents) / 1000)}
                  </td>
                  <td className="text-right">
                    <select value={category || ""}
                      onChange={(e) => e.target.value === "Mixed"
                        ? startAllocation(holding.symbol, holding.allocations)
                        : categorize(holding.symbol, e.target.value)}
                      className={`${inputCls} py-1`}>
                      <option value="">Uncategorized</option>
                      {categories.map((category) => <option key={category}>{category}</option>)}
                      <option value="Mixed">Mixed</option>
                    </select>
                  </td>
                </tr>
                {allocationSymbol === holding.symbol && (
                  <tr>
                    <td colSpan={5} className="bg-slate-50 px-4 py-3">
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
                </React.Fragment>
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
