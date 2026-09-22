import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, NavLink, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import Accounts from "./pages/Accounts";
import Investments from "./pages/Investments";
import Import from "./pages/Import";
import Settings from "./pages/Settings";

export async function api(path: string, opts?: RequestInit) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

const LINKS = ["", "transactions", "accounts",
               "investments", "import", "settings"];

const LABELS: Record<string, string> = {
  "": "dashboard",
  transactions: "spending",
  accounts: "accounts",
  investments: "portfolio",
  import: "import",
  settings: "settings",
};

const SECTIONS: { title: string; links: string[] }[] = [
  { title: "Overview", links: [""] },
  { title: "Spending", links: ["transactions"] },
  { title: "Investing", links: ["investments"] },
  { title: "Manage", links: ["accounts", "import", "settings"] },
];

function linkItem(l: string, activeCls: (a: boolean) => string) {
  return (
    <NavLink key={l} to={`/${l}`} end={l === ""} className={({ isActive }) => activeCls(isActive)}>
      {LABELS[l].replace("-", " ")}
    </NavLink>
  );
}

function links(activeCls: (a: boolean) => string) {
  return LINKS.map((l) => linkItem(l, activeCls));
}

function sectionedLinks(activeCls: (a: boolean) => string) {
  return SECTIONS.map((s) => (
    <div key={s.title} className="pt-3 first:pt-0">
      <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        {s.title}
      </div>
      <div className="space-y-0.5">{s.links.map((l) => linkItem(l, activeCls))}</div>
    </div>
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
        <nav className="flex-1 space-y-0.5 px-3">{sectionedLinks(sideCls)}</nav>
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
          <Route path="/investments" element={<Investments />} />
          <Route path="/portfolio-analysis" element={<Navigate to="/investments" replace />} />
          <Route path="/investment-analysis" element={<Navigate to="/investments" replace />} />
          <Route path="/trade-analysis" element={<Navigate to="/investments" replace />} />
          <Route path="/import" element={<Import />} />
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
