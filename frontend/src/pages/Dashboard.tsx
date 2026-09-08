import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Card, chart, Page, Stat, tooltipStyle, useGet } from "./_shared";

function dollars(cents: any) {
  const n = Number(cents || 0) / 100;
  return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function paceTone(pace: string) {
  return pace === "over" ? "red" : pace === "ahead" ? "amber" : "green";
}

export default function Dashboard() {
  const month = thisMonth();
  const history = useGet("/api/net-worth-history") || [];
  const trends = useGet("/api/reports-trends?months=6") || [];
  const report = useGet(`/api/reports/${month}`);

  const trendRows = (Array.isArray(trends) ? trends : []).map((t: any) => ({
    ...t,
    income: t.income_cents / 100,
    expense: t.expense_cents / 100,
  }));
  const histRows = (Array.isArray(history) ? history : []).map((h: any) => ({
    ...h,
    net: h.net_worth_cents / 100,
  }));
  const budgets = report?.budgets || [];
  const net = report?.net_worth;

  return (
    <Page title="Dashboard">
      {net != null && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Stat label="Net worth">{dollars(net.net_worth_cents)}</Stat>
          <Stat label="Cash">{dollars(net.cash_cents)}</Stat>
          <Stat label="Investments">{dollars(net.investments_cents)}</Stat>
        </div>
      )}
      <Card title="Net worth history">
        {histRows.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={histRows}>
              <CartesianGrid stroke={chart.grid} vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 12, fill: chart.tick }} tickLine={false} axisLine={{ stroke: chart.grid }} />
              <YAxis tickFormatter={(v: number) => `$${v / 1000}k`} tick={{ fontSize: 12, fill: chart.tick }} tickLine={false} axisLine={false} width={52} />
              <Tooltip formatter={(v: any) => dollars(Number(v) * 100)} contentStyle={tooltipStyle} />
              <Line type="monotone" dataKey="net" stroke={chart.net} dot={false} strokeWidth={2.5} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-slate-500">No snapshots yet — run <code>POST /api/snapshots/run</code> to start the series.</p>
        )}
      </Card>
      <Card title="Income vs expense (6 mo)">
        {trendRows.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={trendRows} barCategoryGap="28%">
              <CartesianGrid stroke={chart.grid} vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 12, fill: chart.tick }} tickLine={false} axisLine={{ stroke: chart.grid }} />
              <YAxis tickFormatter={(v: number) => `$${v / 1000}k`} tick={{ fontSize: 12, fill: chart.tick }} tickLine={false} axisLine={false} width={52} />
              <Tooltip formatter={(v: any) => dollars(Number(v) * 100)} contentStyle={tooltipStyle} cursor={{ fill: "#e7ebe6" }} />
              <Bar dataKey="income" fill={chart.income} radius={[4, 4, 0, 0]} />
              <Bar dataKey="expense" fill={chart.expense} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-slate-500">No transactions yet.</p>
        )}
      </Card>
      <Card title={`Budgets (${month})`}>
        {budgets.length > 0 ? (
          <ul className="divide-y divide-slate-100">
            {budgets.map((b: any) => (
              <li key={b.budget_id} className="flex items-center justify-between py-2 text-sm">
                <span>Category {b.category_id}</span>
                <span className="flex items-center gap-2">
                  <span className="text-slate-500 tabular-nums">{dollars(b.spent_cents)} of {dollars(b.effective_cents)}</span>
                  <Badge tone={paceTone(b.pace)}>{b.pace.replace("_", " ")}</Badge>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">No budgets this month.</p>
        )}
      </Card>
    </Page>
  );
}
