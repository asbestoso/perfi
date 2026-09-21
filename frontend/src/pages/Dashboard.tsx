import { Card, Page } from "./_shared";

export default function Dashboard() {
  return (
    <Page title="Dashboard">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card title="Spending">
          <p className="mt-1 text-sm text-slate-500">
            browse and categorize cash moves
          </p>
          <a href="/transactions" className="mt-2 inline-block text-sm font-medium text-pine-700 hover:underline">
            Open spending →
          </a>
        </Card>
        <Card title="Investing">
          <p className="mt-1 text-sm text-slate-500">
            portfolio market value · never counted as spending
          </p>
          <a href="/investments" className="mt-2 inline-block text-sm font-medium text-pine-700 hover:underline">
            Open portfolio →
          </a>
        </Card>
      </div>
      <Card title="Accounts">
        <p className="mt-1 text-sm text-slate-500">
          balances by account across spending and investing
        </p>
        <a href="/accounts" className="mt-2 inline-block text-sm font-medium text-pine-700 hover:underline">
          Open accounts →
        </a>
      </Card>
    </Page>
  );
}
