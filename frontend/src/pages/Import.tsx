import { useState } from "react";
import { api } from "../main";
import { Amt, Badge, btnCls, btnSecCls, btnSmCls, Card, dollars, Empty, inputCls, Page, tblCls, useGet } from "./_shared";

function TransferSuggestions({ tick, onChange }: any) {
  const data = useGet(`/api/transfers/suggestions?tick=${tick}`);
  const [msg, setMsg] = useState("");
  const [dismissed, setDismissed] = useState(false);
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
  const items = (Array.isArray(data) ? data : []).filter(
    (s: any) => !dismissedIds.has(`${s.out_id}-${s.in_id}`)
  );
  async function link(s: any) {
    await api(`/api/transfers/link?out_id=${s.out_id}&in_id=${s.in_id}&transfer_id=t${s.out_id}-${s.in_id}`,
      { method: "POST" });
  }
  async function linkAll() {
    setMsg("Linking high-confidence transfers…");
    try {
      let pending = items.filter((s: any) => s.confidence === "high");
      let linked = 0;
      for (let round = 0; pending.length > 0 && round < 20; round += 1) {
        await Promise.all(pending.map(link));
        linked += pending.length;
        const refreshed = await api(`/api/transfers/suggestions?refresh=${Date.now()}`);
        pending = (Array.isArray(refreshed) ? refreshed : [])
          .filter((s: any) => s.confidence === "high");
      }
      if (pending.length > 0) {
        throw new Error("some transfer suggestions could not be linked");
      }
      setDismissed(true);
      setMsg(`Linked ${linked} high-confidence transfer${linked === 1 ? "" : "s"}.`);
      onChange();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  async function linkOne(s: any) {
    try {
      await link(s);
      setMsg("Transfer linked.");
      onChange();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  function dismiss(s: any) {
    setDismissedIds((ids) => new Set(ids).add(`${s.out_id}-${s.in_id}`));
  }
  if (dismissed || items.length === 0) return null;
  return (
    <Card title={`Transfer suggestions (${items.length})`}>
      <p className="mb-3 text-sm text-slate-500">
        Review these possible transfers before leaving the import flow.
      </p>
      <div className="mb-3 flex items-center gap-2">
        <button onClick={linkAll} className={btnCls}>Link all high-confidence</button>
        {msg && <span className="text-sm text-slate-600">{msg}</span>}
      </div>
      <ul className="divide-y divide-slate-100">
        {items.map((s: any) => (
          <li key={`${s.out_id}-${s.in_id}`} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
            <div className="min-w-0">
              <p className="font-medium">
                {s.outgoing.account} → {s.incoming.account}
                <Badge tone="green">high confidence</Badge>
              </p>
              <p className="text-slate-500">
                {s.outgoing.date} · {s.outgoing.merchant} · {dollars(s.outgoing.amount_cents)}
                <span className="px-2">→</span>
                {s.incoming.date} · {s.incoming.merchant} · {dollars(s.incoming.amount_cents)}
              </p>
            </div>
            <div className="flex gap-1">
              <button onClick={() => linkOne(s)} className={btnSmCls}>Link transfer</button>
              <button onClick={() => dismiss(s)} className={btnSmCls}>Dismiss</button>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

const LAYOUT_KEY = "perfi.importLayouts";

function loadLayouts() {
  try {
    return JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}");
  } catch {
    return {};
  }
}

const MAP_FIELDS = [
  ["date", "Date"], ["merchant", "Description"], ["amount", "Amount"],
  ["type", "Type / action"], ["symbol", "Symbol"], ["quantity", "Quantity"],
  ["price", "Price"], ["account", "Account"], ["category", "Category"],
  ["note", "Note"],
];

const FILE_KINDS = [
  ["mixed", "Mixed"], ["brokerage", "Brokerage only"], ["spending", "Spending only"],
];

async function postScan(file: any, fileKind?: string, mapping?: any) {
  const fd = new FormData();
  fd.append("file", file);
  const qs = new URLSearchParams();
  if (fileKind) qs.set("file_kind", fileKind);
  if (mapping) qs.set("mapping", JSON.stringify(mapping));
  const q = qs.toString();
  return api(q ? `/api/import/scan?${q}` : "/api/import/scan",
    { method: "POST", body: fd });
}

function kindSummary(counts: any) {
  const parts = Object.entries(counts || {}).map(([k, v]) => `${v} ${k.replace("_", " ")}`);
  return parts.length ? parts.join(" · ") : "nothing parseable";
}

function UploadForm({ onDone }: any) {
  const [profile, setProfile] = useState("Holding");
  const [msg, setMsg] = useState("");
  const [holdingFile, setHoldingFile] = useState<any>(null);
  const [holdingAccounts, setHoldingAccounts] = useState<any[]>([]);
  const [holdingLabels, setHoldingLabels] = useState<any[]>([]);
  const [holdingRows, setHoldingRows] = useState<any[]>([]);
  const [holdingMapping, setHoldingMapping] = useState<Record<string, string>>({});
  const [discardedHoldingAccounts, setDiscardedHoldingAccounts] = useState<Set<string>>(new Set());
  const [discardedHoldingRows, setDiscardedHoldingRows] = useState<Set<number>>(new Set());
  const [holdingScanning, setHoldingScanning] = useState(false);
  const [holdingImporting, setHoldingImporting] = useState(false);
  const [creatingAccount, setCreatingAccount] = useState<string | null>(null);
  async function createAccountForImport(label: string) {
    setCreatingAccount(label);
    try {
      const created = await api("/api/accounts", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: label.trim(), type: "other",
          domain: "mixed", balance_cents: 0,
        }),
      });
      setHoldingAccounts((current: any[]) => [
        ...current,
        { id: created.id, name: created.name, type: created.type, domain: created.domain },
      ]);
      setHoldingMapping((current: any) => ({ ...current, [label]: String(created.id) }));
      setMsg("");
    } catch (err: any) {
      if (/: 409\b/.test(err.message || "")) {
        setMsg(`An account named "${label}" already exists — pick it from the list.`);
      } else {
        setMsg(`Could not create account "${label}": ${err.message}`);
      }
    } finally {
      setCreatingAccount(null);
    }
  }
  async function submit(e: any) {
    e.preventDefault();
    setMsg("Uploading…");
    const file = e.target.elements.file.files[0];
    if (!file) { setMsg("Pick a file first."); return; }
    if (profile === "Holding") {
      try {
        setHoldingScanning(true);
        const fd = new FormData();
        fd.append("file", file);
        const result = await api("/api/import/holdings/scan", { method: "POST", body: fd });
        setHoldingFile(file);
        setHoldingAccounts(result.accounts || []);
        setHoldingLabels(result.external_accounts || []);
        setHoldingRows(result.rows || []);
        setHoldingMapping(Object.fromEntries(
          (result.external_accounts || [])
            .filter((item: any) => item.saved_account_id != null)
            .map((item: any) => [item.label, String(item.saved_account_id)])
        ));
        setMsg("");
      } catch (err: any) { setMsg(`Could not read that holdings file: ${err.message}`); }
      finally { setHoldingScanning(false); }
      return;
    }
    setPendingFile(file);
    setMsg("");
    await runScan(file);
  }

  async function importHoldings() {
    const activeLabels = holdingLabels.filter((item) => !discardedHoldingAccounts.has(item.label));
    const activeRows = holdingRows.filter((row) =>
      !discardedHoldingAccounts.has(row.account) && !discardedHoldingRows.has(row.id)
    );
    if (!holdingFile || activeLabels.some((item) => !holdingMapping[item.label])) {
      setMsg("Choose a local account for every account you are importing, or choose Skip.");
      return;
    }
    if (activeRows.length === 0) {
      setMsg("Choose at least one holding to import.");
      return;
    }
    setHoldingImporting(true);
    try {
      const fd = new FormData();
      fd.append("file", holdingFile);
      const mapping = { accounts: Object.fromEntries(
        activeLabels.map((item: any) => [item.label, Number(holdingMapping[item.label])])
      ), excluded_accounts: [...discardedHoldingAccounts],
      excluded_rows: [...discardedHoldingRows]};
      const r = await api(`/api/import/csv?profile=Holding&mapping=${encodeURIComponent(JSON.stringify(mapping))}`,
        { method: "POST", body: fd });
      setMsg(`Committed ${r.updated} holdings across ${r.accounts.length} accounts` +
        `${r.skipped ? `; skipped ${r.skipped}` : ""} (batch ${r.batch_id}).`);
      setHoldingFile(null);
      setHoldingRows([]);
      setDiscardedHoldingAccounts(new Set());
      setDiscardedHoldingRows(new Set());
      onDone(r.batch_id);
    } catch (err: any) { setMsg(`Failed: ${err.message}`); }
    finally { setHoldingImporting(false); }
  }
  // CSV confirmation flow state.
  const [pendingFile, setPendingFile] = useState<any>(null);
  const [scan, setScan] = useState<any>(null);
  const [mapping, setMapping] = useState<any>(null);
  const [fileKind, setFileKind] = useState("mixed");
  const [recognized, setRecognized] = useState<any>(null);
  const [scanning, setScanning] = useState(false);



  async function runScan(file: any, nextKind?: string, nextMapping?: any) {
    setScanning(true);
    try {
      const res = await postScan(file, nextKind, nextMapping);
      setScan(res);
      if (!nextMapping) setMapping(res.mapping);
      if (!nextKind) {
        const saved = loadLayouts()[res.signature];
        if (saved) {
          setRecognized(saved);
          setMapping(saved.mapping);
          setFileKind(saved.file_kind);
          // Refresh the preview counts for the saved kind, not the suggestion.
          const refreshed = await postScan(file, saved.file_kind, saved.mapping);
          setScan(refreshed);
        } else {
          setRecognized(null);
          setFileKind(res.suggested_file_kind);
        }
      }
      setMsg("");
    } catch (err: any) {
      setScan(null);
      setMsg(`Could not read that file: ${err.message}. Check it is a CSV with recognizable columns.`);
    } finally {
      setScanning(false);
    }
  }

  function changeMapping(field: string, column: string) {
    const next = { ...mapping, [field]: column || null };
    setMapping(next);
    if (pendingFile) runScan(pendingFile, fileKind, next);
  }

  function changeKind(nextKind: string) {
    setFileKind(nextKind);
    setRecognized(null);
    if (pendingFile) runScan(pendingFile, nextKind, mapping);
  }

  async function confirmUpload(useSaved?: boolean) {
    if (!pendingFile) return;
    const finalMapping = useSaved ? recognized.mapping : mapping;
    const finalKind = useSaved ? recognized.file_kind : fileKind;
    setMsg("Uploading…");
    try {
      const fd = new FormData();
      fd.append("file", pendingFile);
      const r = await api(
        `/api/import/csv?profile=${profile}&file_kind=${finalKind}&mapping=${encodeURIComponent(JSON.stringify(finalMapping))}`,
        { method: "POST", body: fd }
      );
      const layouts = loadLayouts();
      layouts[scan.signature] = { mapping: finalMapping, file_kind: finalKind, source: scan.detected_source };
      localStorage.setItem(LAYOUT_KEY, JSON.stringify(layouts));
      const merged = await api(`/api/import/batches/${r.batch_id}/merge-safe`, { method: "POST" });
      const accts = (r.accounts || []).join(", ");
      const categories = (r.new_categories || []).join(", ");
      setMsg(`Added ${merged.merged} automatically, held ${merged.held.length} for review (batch ${r.batch_id}: ${kindSummary(r.by_kind)})${accts ? ` → ${accts}` : ""}${categories ? `. New categories: ${categories}` : ""}.`);
      setPendingFile(null);
      setScan(null);
      onDone(r.batch_id);
    } catch (err: any) {
      setMsg(`Failed: ${err.message}`);
    }
  }

  function reset() {
    setPendingFile(null);
    setScan(null);
    setMapping(null);
    setRecognized(null);
    setMsg("");
  }

  const canConfirm = scan && scan.has_date && scan.has_money;
  const moneyUnmapped = scan && (scan.unmapped_columns || []).some((c: string) =>
    /amount|total|price|qty|quantity/i.test(c) && c !== mapping?.amount &&
    c !== mapping?.price && c !== mapping?.quantity);

  return (
    <div className="space-y-3">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <label className="text-sm">Profile
          <select value={profile} onChange={(e) => setProfile(e.target.value)} className={`${inputCls} ml-1`}>
            <option value="Holding">Holding</option>
            <option value="empower">Empower</option>
            <option value="mint">Mint</option>
          </select>
        </label>
        <input name="file" type="file" accept=".csv" className="text-sm text-slate-500 file:mr-2 file:rounded-lg file:border-0 file:bg-pine-800 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-pine-700" />
        <button className={btnCls}>
          {profile === "Holding" ? (holdingScanning ? "Reading…" : "Review accounts") : scanning ? "Scanning…" : "Scan file"}
        </button>
        {msg && <span className="text-sm text-slate-600">{msg}</span>}
      </form>

      {profile === "Holding" && holdingFile && (
        <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-4">
          <div className="mb-3">
            <h3 className="font-medium text-slate-800">Map imported accounts</h3>
            <p className="mt-1 text-sm text-slate-500">
              Choose the account in Perfi that corresponds to each account in this file,
              or create a new one from the dropdown. New accounts are other /
              mixed. Saved matches are preselected for future imports.
            </p>
          </div>
          <div className="space-y-2">
            {holdingLabels.map((item: any) => (
              <div key={item.label} className="grid gap-1 text-sm sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-center sm:gap-3">
                <span className={`truncate font-medium ${discardedHoldingAccounts.has(item.label) ? "text-slate-400 line-through" : "text-slate-700"}`} title={item.label}>{item.label}</span>
                <select
                  value={holdingMapping[item.label] || ""}
                  disabled={discardedHoldingAccounts.has(item.label)}
                  onChange={(e) => {
                    if (e.target.value === "__new__") {
                      createAccountForImport(item.label);
                      return;
                    }
                    setHoldingMapping((current) => ({ ...current, [item.label]: e.target.value }));
                  }}
                  className={inputCls}
                >
                  <option value="">Select a Perfi account…</option>
                  {[...new Set(holdingAccounts.map((account: any) => account.type || "other"))].map(
                    (group: string) => (
                      <optgroup key={group} label={group}>
                        {holdingAccounts
                          .filter((account: any) => (account.type || "other") === group)
                          .map((account: any) => (
                            <option key={account.id} value={account.id}>
                              {account.name}
                            </option>
                          ))}
                      </optgroup>
                    )
                  )}
                  <option value="__new__">
                    {creatingAccount === item.label ? "Creating…" : `+ New account "${item.label}"`}
                  </option>
                </select>
                <button
                  type="button"
                  className={btnSecCls}
                  onClick={() => setDiscardedHoldingAccounts((current) => {
                    const next = new Set(current);
                    if (next.has(item.label)) next.delete(item.label); else next.add(item.label);
                    return next;
                  })}
                >
                  {discardedHoldingAccounts.has(item.label) ? "Include" : "Skip account"}
                </button>
              </div>
            ))}
          </div>
          <div className="mt-5 border-t border-slate-200 pt-4">
            <h4 className="mb-2 text-sm font-medium text-slate-700">Holdings to import</h4>
            <div className="space-y-1">
              {holdingRows.filter((row: any) => !row.known).sort((a: any, b: any) =>
                (Number(String(a.quantity || "").replace(/,/g, "")) || 0) -
                (Number(String(b.quantity || "").replace(/,/g, "")) || 0)
              ).map((row: any) => {
                const accountSkipped = discardedHoldingAccounts.has(row.account);
                const rowSkipped = discardedHoldingRows.has(row.id);
                const skipped = accountSkipped || rowSkipped;
                return (
                  <div key={row.id} className={`grid gap-1 text-sm sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-center sm:gap-3 ${skipped ? "text-slate-400" : "text-slate-600"}`}>
                    <span className={skipped ? "line-through" : ""}>
                      {row.symbol || "(missing symbol)"} · {row.account || "(missing account)"}
                    </span>
                    <span>{row.quantity || "(missing quantity)"}</span>
                    <button
                      type="button"
                      disabled={accountSkipped}
                      className={btnSecCls}
                      onClick={() => setDiscardedHoldingRows((current) => {
                        const next = new Set(current);
                        if (next.has(row.id)) next.delete(row.id); else next.add(row.id);
                        return next;
                      })}
                    >
                      {rowSkipped ? "Include" : "Skip holding"}
                    </button>
                  </div>
                );
              })}
              {holdingRows.every((row: any) => row.known) && (
                <p className="text-sm text-slate-500">
                  All symbols in this file are already known. Existing holdings will still be refreshed.
                </p>
              )}
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button onClick={importHoldings} disabled={holdingImporting} className={btnCls}>
              {holdingImporting ? "Importing…" : "Import holdings"}
            </button>
            <button onClick={() => setHoldingFile(null)} disabled={holdingImporting} className={btnSecCls}>
              Cancel
            </button>
            <span className="text-xs text-slate-500">
              {holdingLabels.length} external account{holdingLabels.length === 1 ? "" : "s"} found
            </span>
          </div>
        </div>
      )}

      {profile !== "Holding" && scan && pendingFile && (
        <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-4">
          {recognized ? (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span>
                Recognized <b>{scan.detected_source}</b> layout — saved mapping will be reused
                ({kindSummary(scan.counts)}).
              </span>
              <button onClick={() => confirmUpload(true)} className={btnCls}>Upload</button>
              <button onClick={() => setRecognized(null)} className={btnSecCls}>Change</button>
              <button onClick={reset} className={btnSmCls}>Cancel</button>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-slate-600">
                New layout detected as <b>{scan.detected_source}</b> ({scan.detection_confidence} confidence).
                Confirm what each column means — nothing is written until you upload.
              </p>
              <div className="flex flex-wrap items-center gap-1">
                <span className="mr-1 text-sm text-slate-600">This file is:</span>
                {FILE_KINDS.map(([v, label]) => (
                  <button key={v} onClick={() => changeKind(v)}
                    className={v === fileKind
                      ? "rounded-md border border-pine-800 bg-pine-800 px-2 py-0.5 text-xs font-medium text-white"
                      : btnSmCls}>
                    {label}
                  </button>
                ))}
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {MAP_FIELDS.map(([field, label]) => (
                  <label key={field} className="flex items-center justify-between gap-2 text-sm">
                    <span className="text-slate-600">{label}</span>
                    <select value={mapping?.[field] || ""}
                      onChange={(e) => changeMapping(field, e.target.value)}
                      className={`${inputCls} w-48`}>
                      <option value="">Ignore</option>
                      {scan.headers.map((h: string) => <option key={h} value={h}>{h}</option>)}
                    </select>
                  </label>
                ))}
              </div>
              <p className="text-sm tabular-nums text-slate-600">
                Preview: {kindSummary(scan.counts)}
                {scan.skipped > 0 && ` · ${scan.skipped} skipped (bad date or amount)`}
              </p>
              {moneyUnmapped && (
                <p className="text-sm font-medium text-amber-800">
                  A money column is unmapped — rows may misclassify. Link Amount (or Price + Quantity) to fix.
                </p>
              )}
              {!canConfirm && (
                <p className="text-sm font-medium text-red-700">
                  {!scan.has_date && !scan.has_money
                    ? "Link a Date column and a money column (Amount, or Price + Quantity) to continue."
                    : !scan.has_date
                      ? "Link a Date column to continue."
                      : "Link a money column (Amount, or Price + Quantity) to continue."}
                </p>
              )}
              {(scan.samples || []).slice(0, 3).map((s: any, i: number) => (
                <div key={i} className="rounded-md bg-white px-3 py-2 text-xs text-slate-600">
                  {MAP_FIELDS.filter(([f]) => s.rendered?.[f]).map(([f, label]) => (
                    <span key={f} className="mr-3"><b>{label}:</b> {s.rendered[f]}</span>
                  ))}
                </div>
              ))}
              <div className="flex gap-2">
                <button onClick={() => confirmUpload()} disabled={!canConfirm} className={btnCls}>
                  Confirm & upload
                </button>
                <button onClick={reset} className={btnSecCls}>Cancel</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function BatchList({ active, onSelect, tick }: any) {
  const data = useGet(`/api/import/batches?tick=${tick}`);
  const items = data?.items || [];
  if (items.length === 0) return <Empty>No imports yet.</Empty>;
  return (
    <ul className="space-y-1">
      {items.map((b: any) => (
        <li key={b.id}>
          <button
            onClick={() => onSelect(b.id)}
            className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-colors ${
              active === b.id ? "bg-pine-100/60 font-semibold" : "hover:bg-slate-50"
            }`}
          >
            <span>
              #{b.id} · {new Date(b.created_at).toLocaleString()} · {b.filename || "(upload)"}
              <span className="text-slate-500"> · {b.profile}</span>
            </span>
            <span className="flex items-center gap-2 text-slate-500 tabular-nums">
              {b.committed} committed · {b.skipped} skipped
              {b.status === "rolled_back" && " · rolled back"}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function RowQueue({ batchId, tick, onChange }: any) {
  const [filter, setFilter] = useState("pending");
  const [kindFilter, setKindFilter] = useState("");
  const [review, setReview] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const kindQs = kindFilter ? `&kind=${kindFilter}` : "";
  const data = useGet(`/api/import/batches/${batchId}/rows?status=${filter}${kindQs}&tick=${tick}`);
  const rows = data?.items || [];
  async function act(id: number, action: string) {
    await api(`/api/import/batches/${batchId}/resolve?staging_id=${id}&action=${action}`, { method: "POST" });
    onChange();
  }
  async function mergeAll() {
    setMsg("Merging…");
    try {
      await api(`/api/import/batches/${batchId}/merge-all`, { method: "POST" });
      setMsg("");
      onChange();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  async function checkReview() {
    setMsg("Checking…");
    try {
      const r = await api(`/api/import/batches/${batchId}/review`);
      setReview(r);
      setMsg("");
      return r;
    } catch (e: any) { setMsg(`Failed: ${e.message}`); return null; }
  }
  async function mergeSafe() {
    setMsg("Merging safe rows…");
    try {
      const r = await api(`/api/import/batches/${batchId}/merge-safe`, { method: "POST" });
      await checkReview();
      setMsg(`Merged ${r.merged}, held ${r.held.length} for review.`);
      onChange();
    } catch (e: any) { setMsg(`Failed: ${e.message}`); }
  }
  const byId: any = {};
  rows.forEach((r: any) => { byId[r.id] = r; });
  const statusTone = (s: string) => s === "merged" ? "green" : s === "discarded" ? "slate" : "amber";
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <select value={filter} onChange={(e) => setFilter(e.target.value)} className={inputCls}>
          <option value="pending">Pending</option>
          <option value="duplicate">Duplicates</option>
          <option value="merged">Merged</option>
          <option value="discarded">Discarded</option>
        </select>
        <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)} className={inputCls}>
          <option value="">All kinds</option>
          <option value="spend">Spend</option>
          <option value="brokerage_cash">Brokerage cash</option>
          <option value="unknown">Needs review</option>
        </select>
        <button onClick={checkReview} className={btnSecCls}>
          Review
        </button>
        <button onClick={mergeSafe} className={btnCls}>
          Merge safe
        </button>
        <button onClick={mergeAll} className={btnSecCls}>
          Merge all pending
        </button>
        {msg && <span className="text-sm text-slate-600">{msg}</span>}
      </div>
      {review && (
        <p className="mb-2 text-sm text-slate-600">
          <b className="tabular-nums">{review.safe}</b> safe, <b className="tabular-nums">{review.needs_review}</b> need review.
          {review.needs_review > 0 && " Merge safe leaves the ones below pending."}
        </p>
      )}
      {review?.suspects?.length > 0 && (
        <ul className="mb-3 divide-y divide-amber-100 rounded-xl border border-amber-300 bg-amber-50 px-4">
          {review.suspects.map((s: any) => (
            <li key={s.staging_id} className="py-2 text-sm">
              <span className="font-medium">
                {s.merchant || byId[s.staging_id]?.merchant || `#${s.staging_id}`} · {s.date || byId[s.staging_id]?.date || ""} · {dollars(s.amount_cents ?? byId[s.staging_id]?.amount_cents)}
              </span>
              {s.status === "duplicate" && <Badge tone="amber">duplicate</Badge>}
              <ul className="list-disc pl-5 text-xs text-amber-900">
                {s.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}
              </ul>
            </li>
          ))}
        </ul>
      )}
      {rows.length === 0 ? (
        <Empty>Nothing here.</Empty>
      ) : (
        <table className={tblCls}>
          <thead>
            <tr>
              <th>Date</th><th>Merchant</th>
              <th className="text-right">Amount</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r: any) => (
              <tr key={r.id}>
                <td className="whitespace-nowrap tabular-nums text-slate-600">{r.date}</td>
                <td className="font-medium">{r.merchant}</td>
                <td className="text-right"><Amt cents={r.amount_cents} /></td>
                <td><Badge tone={statusTone(r.status)}>{r.status}</Badge></td>
                <td className="space-x-1 text-right">
                  {(r.status === "pending" || r.status === "duplicate") && (
                    <>
                      <button onClick={() => act(r.id, "merge")} className={btnSmCls}>Merge</button>
                      <button onClick={() => act(r.id, "discard")} className={btnSmCls}>Discard</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function UnknownQueue({ batchId, tick, onChange }: any) {
  const data = useGet(`/api/import/batches/${batchId}/rows?kind=unknown&status=pending&tick=${tick}`);
  const rows = data?.items || [];
  if (rows.length === 0) return null;
  async function discard(id: number) {
    await api(`/api/import/batches/${batchId}/resolve?staging_id=${id}&action=discard`,
      { method: "POST" });
    onChange();
  }
  return (
    <Card title={`Needs review (${rows.length})`}>
      <p className="mb-2 text-sm text-slate-500">
        Unrecognized activity — these never post automatically. Discard what you don't need.
      </p>
      <ul className="divide-y divide-slate-100">
        {rows.map((r: any) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
            <div>
              <span className="font-medium">{r.merchant}</span>
              <span className="text-slate-500"> · {r.date} · </span>
              <Amt cents={r.amount_cents} />
              {r.row_detail && <div className="text-xs text-amber-800">{r.row_detail}</div>}
            </div>
            <button onClick={() => discard(r.id)} className={btnSmCls}>Discard</button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function BatchChanges({ batchId, tick }: any) {
  const data = useGet(`/api/import/batches/${batchId}/changes?tick=${tick}`);
  if (!data || data.error || !data.changes) return null;
  if (data.changes.length === 0) return (
    <p className="text-sm text-slate-500">No holdings changed in this import.</p>
  );
  const qty = (m: number) => (m / 1000).toLocaleString();
  return (
    <table className={tblCls}>
      <thead><tr><th>Account</th><th>Holding</th>
        <th className="text-right">Before</th><th className="text-right">Imported</th>
        <th className="text-right">Now</th>
      </tr></thead>
      <tbody>
        {data.changes.map((c: any) => (
          <tr key={`${c.account_id}-${c.symbol}`}>
            <td>{c.account_name}</td>
            <td>{c.symbol}{c.added && " (new)"}</td>
            <td className="text-right tabular-nums">{qty(c.previous_quantity_milli)}</td>
            <td className="text-right tabular-nums">{qty(c.quantity_milli)}</td>
            <td className="text-right tabular-nums">
              {c.current_quantity_milli == null
                ? "removed"
                : c.current_quantity_milli === c.quantity_milli
                  ? "—"
                  : `${qty(c.current_quantity_milli)} (edited since)`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BatchSummary({ batchId, tick, onChange }: any) {
  const data = useGet(`/api/import/batches/${batchId}?tick=${tick}`);
  if (!data || data.error) return null;
  async function rollback() {
    if (!window.confirm(
      `Roll back batch #${batchId}? This removes records created by this import and cannot be undone.`
    )) return;
    try {
      await api(`/api/import/batches/${batchId}/rollback`, { method: "POST" });
      onChange();
    } catch (e: any) {
      window.alert(`Rollback failed: ${e.message}`);
    }
  }
  return (
    <div className="mb-2 flex flex-wrap items-center gap-3 text-sm text-slate-500">
      <span>
        {new Date(data.created_at).toLocaleString()} · {data.profile} · {data.file_kind} file ·
        {data.committed} committed
        {data.skipped > 0 && ` · ${data.skipped} skipped`}
        {data.status === "rolled_back" && " · rolled back"}
      </span>
      {data.status !== "rolled_back" && (
        <button onClick={rollback} className={btnSmCls}>Roll back import</button>
      )}
    </div>
  );
}

function BatchDetail({ batchId, tick, onChange }: any) {
  const data = useGet(`/api/import/batches/${batchId}?tick=${tick}`);
  if (!data || data.error) return null;
  if (data.profile === "Holding") {
    return (
      <Card title={`Batch #${batchId} changes`}>
        <BatchSummary batchId={batchId} tick={tick} onChange={onChange} />
        <BatchChanges batchId={batchId} tick={tick} />
      </Card>
    );
  }
  return (
    <>
      <UnknownQueue batchId={batchId} tick={tick} onChange={onChange} />
      <Card title={`Batch #${batchId} rows`}>
        <BatchSummary batchId={batchId} tick={tick} onChange={onChange} />
        <RowQueue batchId={batchId} tick={tick} onChange={onChange} />
      </Card>
    </>
  );
}

export default function Import() {
  const [batchId, setBatchId] = useState<number | null>(null);
  const [tick, setTick] = useState(0);
  const bump = () => setTick((t) => t + 1);

  return (
    <Page title="Import">
      <TransferSuggestions tick={tick} onChange={bump} />
      <Card title="Upload">
        <p className="mb-2 text-sm text-slate-500">
          Bank statements and brokerage activity exports land here. New layouts ask you to
          confirm the columns first; known layouts upload straight through.
          Accounts are matched by name and created if new.
        </p>
        <UploadForm onDone={(id: number) => { setBatchId(id); bump(); }} />
      </Card>
      <Card title="Batches">
        <BatchList active={batchId} onSelect={setBatchId} tick={tick} />
      </Card>
      {batchId != null && (
        <BatchDetail batchId={batchId} tick={tick} onChange={bump} />
      )}
    </Page>
  );
}
