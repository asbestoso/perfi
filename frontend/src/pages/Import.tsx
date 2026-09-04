import { useState } from "react";
import { api } from "../main";
import { Card, Page, useGet } from "./_shared";

function dollars(cents: any) {
  return (Number(cents || 0) / 100).toLocaleString(undefined, {
    style: "currency", currency: "USD",
  });
}

function UploadForm({ onDone }: any) {
  const [profile, setProfile] = useState("generic");
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
      const accts = (r.accounts || []).join(", ");
      setMsg(`Staged ${r.staged}, skipped ${r.skipped} (batch ${r.batch_id})${accts ? ` → ${accts}` : ""}.`);
      onDone();
    } catch (err: any) {
      setMsg(`Failed: ${err.message}`);
    }
  }
  const input = "rounded-md border border-slate-300 px-2 py-1 text-sm";
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
      <label className="text-sm">Type
        <select value={kind} onChange={(e) => setKind(e.target.value)} className={`${input} ml-1`}>
          <option value="csv">CSV</option>
          <option value="ofx">OFX</option>
        </select>
      </label>
      {kind === "csv" && (
        <label className="text-sm">Profile
          <select value={profile} onChange={(e) => setProfile(e.target.value)} className={`${input} ml-1`}>
            <option value="generic">Generic</option>
            <option value="mint">Mint</option>
            <option value="empower">Empower</option>
            <option value="monarch">Monarch</option>
          </select>
        </label>
      )}
      <input name="file" type="file" accept={kind === "csv" ? ".csv" : ".ofx,.qfx"} className="text-sm text-slate-500 file:mr-2 file:rounded-md file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-sm file:text-white hover:file:bg-slate-700" />
      <button className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700">Upload</button>
      {msg && <span className="text-sm text-slate-600">{msg}</span>}
    </form>
  );
}

function BatchList({ active, onSelect, tick }: any) {
  const data = useGet(`/api/import/batches?tick=${tick}`);
  const items = data?.items || [];
  if (items.length === 0) return <p className="text-sm text-slate-500">No imports yet.</p>;
  return (
    <ul className="divide-y divide-slate-100">
      {items.map((b: any) => (
        <li key={b.id}>
          <button
            onClick={() => onSelect(b.id)}
            className={`flex w-full items-center justify-between py-2 text-left text-sm hover:bg-slate-50 ${
              active === b.id ? "font-semibold" : ""
            }`}
          >
            <span>#{b.id} {b.filename || "(upload)"} · {b.profile}</span>
            <span className="text-slate-500">staged {b.staged} · skipped {b.skipped}</span>
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
  const btn = "rounded-md border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-100";
  const byId: any = {};
  rows.forEach((r: any) => { byId[r.id] = r; });
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <select value={filter} onChange={(e) => setFilter(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1 text-sm">
          <option value="pending">Pending</option>
          <option value="merged">Merged</option>
          <option value="discarded">Discarded</option>
        </select>
        <button onClick={checkReview} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100">
          Review
        </button>
        <button onClick={mergeSafe} className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700">
          Merge safe
        </button>
        <button onClick={mergeAll} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100">
          Merge all pending
        </button>
        {msg && <span className="text-sm text-slate-600">{msg}</span>}
      </div>
      {review && (
        <p className="mb-2 text-sm text-slate-600">
          {review.safe} safe, {review.needs_review} need review.
          {review.needs_review > 0 && " Merge safe leaves the ones below pending."}
        </p>
      )}
      {review?.suspects?.length > 0 && (
        <ul className="mb-3 divide-y divide-slate-100 rounded-md border border-amber-200 bg-amber-50 px-3">
          {review.suspects.map((s: any) => (
            <li key={s.staging_id} className="py-1.5 text-sm">
              <span className="font-medium">
                {byId[s.staging_id]?.merchant || `#${s.staging_id}`} · {byId[s.staging_id]?.date || ""} · {byId[s.staging_id] != null ? dollars(byId[s.staging_id].amount_cents) : ""}
              </span>
              <ul className="list-disc pl-5 text-xs text-slate-600">
                {s.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}
              </ul>
            </li>
          ))}
        </ul>
      )}
      {rows.length === 0 ? (
        <p className="text-sm text-slate-500">Nothing here.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-slate-500">
              <th className="py-1">Date</th><th>Merchant</th>
              <th className="text-right">Amount</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r: any) => (
              <tr key={r.id}>
                <td className="py-1">{r.date}</td>
                <td>{r.merchant}</td>
                <td className="text-right">{dollars(r.amount_cents)}</td>
                <td className="text-slate-500">{r.status}</td>
                <td className="space-x-1 text-right">
                  {r.status === "pending" && (
                    <>
                      <button onClick={() => act(r.id, "merge")} className={btn}>Merge</button>
                      <button onClick={() => act(r.id, "discard")} className={btn}>Discard</button>
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
      <Card title="Upload">
        <p className="mb-2 text-sm text-slate-500">
          Accounts are matched by name from the file and created if new. Use the Monarch profile for Monarch exports.
        </p>
        <UploadForm onDone={bump} />
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
