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
      await Promise.all(items.filter((s: any) => s.confidence === "high").map(link));
      setDismissed(true);
      setMsg(`Linked ${items.length} high-confidence transfer${items.length === 1 ? "" : "s"}.`);
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

function UploadForm({ onDone }: any) {
  const [profile, setProfile] = useState("empower");
  const [kind, setKind] = useState("csv");
  const [msg, setMsg] = useState("");
  async function submit(e: any) {
    e.preventDefault();
    setMsg("Uploading…");
    const file = e.target.elements.file.files[0];
    if (!file) { setMsg("Pick a file first."); return; }
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api(
        `/api/import/${kind}?profile=${profile}`,
        { method: "POST", body: fd }
      );
      const merged = await api(`/api/import/batches/${r.batch_id}/merge-safe`, { method: "POST" });
      const accts = (r.accounts || []).join(", ");
      const categories = (r.new_categories || []).join(", ");
      setMsg(`Added ${merged.merged} automatically, held ${merged.held.length} for review (batch ${r.batch_id})${accts ? ` → ${accts}` : ""}${categories ? `. New categories: ${categories}` : ""}.`);
      onDone(r.batch_id);
    } catch (err: any) {
      setMsg(`Failed: ${err.message}`);
    }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
      <label className="text-sm">Type
        <select value={kind} onChange={(e) => setKind(e.target.value)} className={`${inputCls} ml-1`}>
          <option value="csv">CSV</option>
          <option value="ofx">OFX</option>
        </select>
      </label>
      {kind === "csv" && (
        <label className="text-sm">Profile
          <select value={profile} onChange={(e) => setProfile(e.target.value)} className={`${inputCls} ml-1`}>
            <option value="empower">Empower</option>
            <option value="mint">Mint</option>
          </select>
        </label>
      )}
      <input name="file" type="file" accept={kind === "csv" ? ".csv" : ".ofx,.qfx"} className="text-sm text-slate-500 file:mr-2 file:rounded-lg file:border-0 file:bg-pine-800 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-pine-700" />
      <button className={btnCls}>Upload</button>
      {msg && <span className="text-sm text-slate-600">{msg}</span>}
    </form>
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
            <span>#{b.id} {b.filename || "(upload)"} · {b.profile}</span>
            <span className="flex items-center gap-2 text-slate-500 tabular-nums">
              staged {b.staged} · skipped {b.skipped}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function RowQueue({ batchId, tick, onChange }: any) {
  const [filter, setFilter] = useState("pending");
  const [review, setReview] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const data = useGet(`/api/import/batches/${batchId}/rows?status=${filter}&tick=${tick}`);
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

export default function Import() {
  const [batchId, setBatchId] = useState<number | null>(null);
  const [tick, setTick] = useState(0);
  const bump = () => setTick((t) => t + 1);

  return (
    <Page title="Import">
    <TransferSuggestions tick={tick} onChange={bump} />
    <Card title="Upload">
        <p className="mb-2 text-sm text-slate-500">
          Accounts are matched by name from the file and created if new. Empower is the default CSV profile.
        </p>
        <UploadForm onDone={(id: number) => { setBatchId(id); bump(); }} />
      </Card>
      <Card title="Batches">
        <BatchList active={batchId} onSelect={setBatchId} tick={tick} />
      </Card>
      {batchId != null && (
        <Card title={`Batch #${batchId} rows`}>
          <RowQueue batchId={batchId} tick={tick} onChange={bump} />
        </Card>
      )}
    </Page>
  );
}
