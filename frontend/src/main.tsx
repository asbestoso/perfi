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
import Import from "./pages/Import";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";

export async function api(path: string, opts?: RequestInit) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

const LINKS = ["", "transactions", "accounts", "budgets", "recurring",
               "investments", "import", "reports", "settings"];

function Nav() {
  return (
    <header className="bg-slate-900 text-slate-100">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-1 px-4 py-3">
        <span className="mr-4 text-lg font-bold tracking-tight">perfi</span>
        {LINKS.map((l) => (
          <NavLink
            key={l}
            to={`/${l}`}
            end={l === ""}
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 text-sm capitalize transition-colors ${
                isActive ? "bg-slate-700 text-white" : "text-slate-300 hover:bg-slate-800 hover:text-white"
              }`
            }
          >
            {l || "dashboard"}
          </NavLink>
        ))}
      </div>
    </header>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen">
        <Nav />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/accounts" element={<Accounts />} />
          <Route path="/budgets" element={<Budgets />} />
          <Route path="/recurring" element={<Recurring />} />
          <Route path="/import" element={<Import />} />
          <Route path="/investments" element={<Investments />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
