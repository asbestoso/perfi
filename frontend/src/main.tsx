import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import "./index.css";
import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import Accounts from "./pages/Accounts";
import Budgets from "./pages/Budgets";
import Recurring from "./pages/Recurring";
import Investments from "./pages/Investments";
import InvestmentAnalysis from "./pages/InvestmentAnalysis";
import Import from "./pages/Import";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";

export async function api(path: string, opts?: RequestInit) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

const LINKS = ["", "transactions", "accounts", "budgets", "recurring",
               "investments", "investment-analysis", "import", "reports", "settings"];

function links(activeCls: (a: boolean) => string) {
  return LINKS.map((l) => (
    <NavLink key={l} to={`/${l}`} end={l === ""} className={({ isActive }) => activeCls(isActive)}>
      {(l || "dashboard").replace("-", " ")}
    </NavLink>
  ));
}

const sideCls = (a: boolean) =>
  `block rounded-lg px-3 py-2 text-sm capitalize transition-colors ${
    a ? "bg-pine-800 font-medium text-white" : "text-slate-400 hover:bg-white/5 hover:text-white"
  }`;
const topCls = (a: boolean) =>
  `rounded-md px-3 py-1.5 text-sm capitalize transition-colors ${
    a ? "bg-white/10 font-medium text-white" : "text-slate-300 hover:bg-white/5 hover:text-white"
  }`;

function Shell() {
  return (
    <div className="min-h-screen md:flex">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col bg-ink-900 md:flex">
        <div className="flex items-center gap-2.5 px-5 pb-6 pt-6">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-pine-700 text-sm font-bold text-white">
            pf
          </span>
          <span className="text-lg font-bold tracking-tight text-white">perfi</span>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">{links(sideCls)}</nav>
        <div className="px-5 py-4 text-xs text-slate-500">local-first finance</div>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="bg-ink-900 text-slate-100 md:hidden">
          <div className="flex items-center gap-1 overflow-x-auto px-3 py-2.5">
            <span className="mr-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-pine-700 text-xs font-bold text-white">
              pf
            </span>
            {links(topCls)}
          </div>
        </header>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/accounts" element={<Accounts />} />
          <Route path="/budgets" element={<Budgets />} />
          <Route path="/recurring" element={<Recurring />} />
          <Route path="/investments" element={<Investments />} />
          <Route path="/investment-analysis" element={<InvestmentAnalysis />} />
          <Route path="/import" element={<Import />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </div>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
