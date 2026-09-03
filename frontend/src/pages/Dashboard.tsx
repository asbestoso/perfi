import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, Page, useGet } from "./_shared";

function dollars(cents: any) {
  const n = Number(cents || 0) / 100;
  return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function paceBadge(pace: string) {
  const color = pace === "over" ? "bg-red-100 text-red-800"
    : pace === "ahead" ? "bg-amber-100 text-amber-800"
    : "bg-green-100 text-green-800";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>{pace.replace("_", " ")}</span>;
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
          {[
            ["Net worth", net.net_worth_cents],
            ["Cash", net.cash_cents],
            ["Investments", net.investments_cents],
          ].map(([label, cents]) => (
            <div key={label} className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
              <div className="text-sm text-slate-500">{label}</div>
              <div className="text-2xl font-bold">{dollars(cents)}</div>
            </div>
          ))}
        </div>
      )}
      <Card title="Net worth history">
        {histRows.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={histRows}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={(v: number) => `$${v / 1000}k`} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v: any) => dollars(Number(v) * 100)} />
              <Line type="monotone" dataKey="net" stroke="#2563eb" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-slate-500">No snapshots yet — run <code>POST /api/snapshots/run</code> to start the series.</p>
        )}
      </Card>
      <Card title="Income vs expense (6 mo)">
        {trendRows.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={trendRows}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={(v: number) => `$${v / 1000}k`} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v: any) => dollars(Number(v) * 100)} />
              <Bar dataKey="income" fill="#16a34a" radius={[4, 4, 0, 0]} />
              <Bar dataKey="expense" fill="#dc2626" radius={[4, 4, 0, 0]} />
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
                  <span className="text-slate-500">{dollars(b.spent_cents)} of {dollars(b.effective_cents)}</span>
                  {paceBadge(b.pace)}
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
