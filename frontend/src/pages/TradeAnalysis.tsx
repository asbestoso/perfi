import { dollars, Empty, Error, Page, tblCls, useGet } from "./_shared";

function shares(milli: any) {
  return (Number(milli || 0) / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function percent(value: any) {
  return `${Number(value || 0) >= 0 ? "+" : ""}${Number(value || 0).toFixed(1)}%`;
}

function annualizedPercent(value: any) {
  return value == null ? "—" : percent(value);
}

export default function TradeAnalysis() {
  const data = useGet("/api/investment-orders/analysis");
  const items = data?.items || [];

  return (
    <Page title="Trade analysis" sub="Review order-level performance and current value.">
      <section className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(16,24,32,0.06)]">
        <div className="mb-3">
          <h2 className="text-base font-semibold tracking-tight">Orders ({items.length})</h2>
          <p className="mt-0.5 text-sm text-slate-500">
            Buy orders use the latest quote for market value; sells use realized proceeds
            against your average buy price. Simple trade P&amp;L, not tax lots.
          </p>
        </div>
        <Error data={data} />
        {items.length === 0 ? <Empty>No orders yet — add one from the Investments tab.</Empty> : (
          <div className="overflow-x-auto">
            <table className={tblCls}>
              <thead>
                <tr>
                  <th>Date</th><th>Symbol</th><th>Account</th><th>Action</th>
                  <th className="text-right">Shares</th><th className="text-right">Market value</th>
                  <th className="text-right">Cost</th><th className="text-right">Gain / loss</th>
                  <th className="text-right">Percent</th><th className="text-right">Annualized</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item: any) => (
                  <tr key={item.id}>
                    <td>{item.executed_at}</td>
                    <td className="font-medium">{item.symbol}</td>
                    <td>{item.account_name}</td>
                    <td className={item.side === "buy" ? "text-pine-700" : "text-slate-600"}>
                      {item.side}
                    </td>
                    <td className="text-right tabular-nums">{shares(item.quantity_milli)}</td>
                    <td className="text-right tabular-nums">{dollars(item.market_value_cents)}</td>
                    <td className="text-right tabular-nums">{dollars(item.cost_cents)}</td>
                    <td className={`text-right tabular-nums ${item.gain_cents >= 0 ? "text-pine-700" : "text-red-700"}`}>
                      {dollars(item.gain_cents)}
                    </td>
                    <td className={`text-right tabular-nums ${item.percent >= 0 ? "text-pine-700" : "text-red-700"}`}>
                      {percent(item.percent)}
                    </td>
                    <td className={`text-right tabular-nums ${item.annualized_percent == null
                      ? "text-slate-400" : item.annualized_percent >= 0 ? "text-pine-700" : "text-red-700"}`}>
                      {annualizedPercent(item.annualized_percent)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </Page>
  );
}
