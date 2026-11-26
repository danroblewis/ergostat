import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, ErrorNote, Loading, Note, Page, Select } from "../../components";
import { asQueryPanel, DashboardView, normalizeDashboard, normalizePanel, type DashboardDef, type PanelDef } from "../../components/panels";
import { useApi } from "../../hooks/useApi";
import { apiGet, apiPost, apiSend, isPublic } from "../../lib/api";
import { diagramOf } from "../../lib/hrefs";
import type { Panel } from "../../lib/query";
import { useStatus } from "../../state/status";
import { Editor } from "./Editor";
import { defaultDashboard, MOST, queuesOf } from "./lib/defaults";

/* The Dashboard: a grid of panels of any kind (components/panels), each asking for its own answer. Two kinds of
   dashboard: this browser's draft (kept here, with none kept the default built from what the record holds), and those
   the model declares under `dashboards:` (SPEC §4f), opened by name (?name=NAME) and drawn as declared. Keep sends the
   draft to the server, which works out its `dashboards:` entry; the owner Accepts it here and the model holds it. */

const EVERY: Record<string, number> = { Off: 0, "10s": 10000, "30s": 30000, "1m": 60000, "5m": 300000 };
const keyOf = (name: string) => `ergostat.dashboard.${name}`;

function stored(name: string): DashboardDef | null {
  try {
    const d = JSON.parse(localStorage.getItem(keyOf(name)) || "null");
    return d && Array.isArray(d.panels) ? normalizeDashboard(d) : null;
  } catch { return null; }
}
function store(name: string, d: DashboardDef | null): void {
  try { if (d) localStorage.setItem(keyOf(name), JSON.stringify(d)); else localStorage.removeItem(keyOf(name)); } catch { /* kept for this visit only */ }
}

/** A panel as the editor edits it (the query engine's Panel; a diagram as form "diagram"), and back. */
const forEditor = (def: PanelDef): Panel =>
  def.panel === "diagram" ? { ...asQueryPanel(def), form: "diagram", diagram: diagramOf(def.address || "/diagram") } : asQueryPanel(def);
const EDITABLE = new Set(["query", "diagram"]);

export default function DashboardPage() {
  const [q] = useSearchParams();
  const name = q.get("name");
  return name ? <Declared name={name} /> : <Draft />;
}

/** Which dashboard: this browser's draft, or one the model declares. */
function Chooser({ name }: { name: string | null }) {
  const list = useApi<any[]>("dashboards", {}, { window: false });
  const navigate = useNavigate();
  const options = [{ value: "", label: "This browser's draft" }, ...(list.data || []).map((d) => ({ value: d.name, label: d.title || d.name }))];
  return (
    <label className="muted small">Dashboard <Select aria-label="Dashboard" value={name || ""} options={options}
      onChange={(e) => navigate(e.target.value ? `/dashboard?name=${encodeURIComponent(e.target.value)}` : "/dashboard")} /></label>
  );
}

function Refresh({ every, setEvery, onNow }: { every: string; setEvery: (v: string) => void; onNow: () => void }) {
  return (
    <>
      <label className="muted small">Refresh <Select value={every} onChange={(e) => setEvery(e.target.value)} options={Object.keys(EVERY)} /></label>
      <Button onClick={onNow}>Refresh now</Button>
    </>
  );
}

/** A dashboard the model declares, drawn as declared; Edit a copy makes it this browser's draft. */
function Declared({ name }: { name: string }) {
  const got = useApi<any>(`dashboard/${encodeURIComponent(name)}`, {}, { window: false });
  const { status } = useStatus();
  const navigate = useNavigate();
  const [every, setEvery] = useState("30s");
  const [refreshed, setRefreshed] = useState(0);
  const d = got.data ? normalizeDashboard({ ...got.data, panels: (got.data.panels || []).map((x: any) => x.panel) }) : null;
  const copy = () => {
    if (!d || status?.name == null) return;
    store(status.name, { ...d, title: d.title, panels: d.panels });
    navigate("/dashboard?edit=1");
  };
  const actions = (
    <span className="dash-actions">
      <Chooser name={name} />
      <Refresh every={every} setEvery={setEvery} onNow={() => setRefreshed((n) => n + 1)} />
      <Button onClick={copy} disabled={!d} title="Make a copy of it this browser's draft, to change">Edit a copy</Button>
    </span>
  );
  return (
    <Page title={d?.title || name} actions={actions} className="dash">
      {got.error && <ErrorNote error={got.error} />}
      {!d && !got.error && <Loading />}
      {got.data?.description && <Note>{got.data.description}</Note>}
      {d && <DashboardView panels={d.panels} every={EVERY[every] || null} refreshKey={refreshed} />}
    </Page>
  );
}

/** This browser's draft: edited here, kept here, and sent to the model with Keep. */
function Draft() {
  const { status } = useStatus();
  const name = status?.name;
  const [q, setQ] = useSearchParams();
  const [d, setD] = useState<DashboardDef | null>(null);
  const [failed, setFailed] = useState<Error | null>(null);
  const [editing, setEditing] = useState(q.get("edit") === "1");
  const [open, setOpen] = useState<Panel | null>(null);
  const [every, setEvery] = useState("30s");
  const [refreshed, setRefreshed] = useState(0);
  const [keeping, setKeeping] = useState(false);

  useEffect(() => {
    if (q.get("edit")) setQ((p) => { const n = new URLSearchParams(p); n.delete("edit"); return n; }, { replace: true });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (name == null || d) return;
    const kept = stored(name);
    if (kept) { setD(kept); return; }
    let gone = false;
    (async () => {
      const fields = await apiGet("query/fields");
      const infos = (await apiGet("items", { n: 1, eta: 0 }).catch(() => null))?.kinds || [];
      if (!gone) setD(normalizeDashboard(defaultDashboard(fields, infos, queuesOf(fields, infos))));
    })().catch((e) => { if (!gone) setFailed(e); });
    return () => { gone = true; };
  }, [name, d]);

  const change = (next: DashboardDef) => { setD(next); if (name != null) store(name, next); };
  const panels = d?.panels || [];

  const save = (p: Panel) => {
    if (!d) return;
    const def = normalizePanel(p);
    const has = d.panels.some((x) => x.id === def.id);
    change({ ...d, panels: has ? d.panels.map((x) => (x.id === def.id ? def : x)) : [...d.panels, def] });
    setOpen(null);
  };
  const remove = (id?: string) => d && change({ ...d, panels: d.panels.filter((x) => x.id !== id) });
  const move = (id: string | undefined, by: -1 | 1) => {
    if (!d) return;
    const list = [...d.panels], i = list.findIndex((x) => x.id === id), j = i + by;
    if (i < 0 || j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    change({ ...d, panels: list });
  };
  const fresh = (): Panel => {
    let n = panels.length + 1;
    while (panels.some((x) => x.id === `p${n}`)) n++;
    return { id: `p${n}`, title: "", note: "", form: "line", size: "m", queries: [], display: {} };
  };

  const actions = (
    <span className="dash-actions">
      <Chooser name={null} />
      <Refresh every={every} setEvery={setEvery} onNow={() => setRefreshed((n) => n + 1)} />
      {editing && <Button onClick={() => setOpen(fresh())} disabled={panels.length >= MOST}>Add panel</Button>}
      {editing && d && name != null && (
        <Button onClick={() => { store(name, null); setD(null); }} title="Forget this browser's dashboard and build the default again">Reset to default</Button>
      )}
      {d && !isPublic() && <Button onClick={() => setKeeping(true)} title="Keep it in the model, under dashboards:, for everyone">Keep</Button>}
      <Button className={`dash-edit${editing ? " on" : ""}`} aria-pressed={editing} onClick={() => setEditing(!editing)}>{editing ? "Done" : "Edit"}</Button>
    </span>
  );

  return (
    <Page title={d?.title || "Dashboard"} actions={actions} className="dash">
      <ErrorNote error={failed} />
      {!d && !failed && <Loading />}
      {keeping && d && <KeepBox d={d} onClose={() => setKeeping(false)} />}
      {d && !panels.length && <Note>No panels. Choose Edit, then Add panel.</Note>}
      <DashboardView panels={panels} every={EVERY[every] || null} refreshKey={refreshed}
        tools={(def) => editing && (
          <EditTools def={def} onEdit={EDITABLE.has(def.panel) ? () => setOpen(forEditor(def)) : undefined}
            onRemove={() => remove(def.id)} onMove={(by) => move(def.id, by)} />
        )} />
      {open && <Editor panel={open} onSave={save} onCancel={() => setOpen(null)} />}
    </Page>
  );
}

/** Keep: the draft sent to the server, which works out its `dashboards:` entry and shows the change; Accept writes
 *  it to the model, Dismiss lets it go. Nothing is written before Accept. */
function KeepBox({ d, onClose }: { d: DashboardDef; onClose: () => void }) {
  const navigate = useNavigate();
  const [x, setX] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    apiSend("propose", { title: d.title, since: d.since ?? undefined, panels: d.panels }, { keep: "dashboard" })
      .then(setX).catch((e) => setError(String(e.message || e)));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const answer = async (what: "accept" | "dismiss") => {
    setBusy(true);
    try {
      await apiPost(`proposals/${encodeURIComponent(x.id)}/${what}`);
      if (what === "accept") navigate(`/dashboard?name=${encodeURIComponent(String(x.target).replace(/^dashboard\./, ""))}`);
      else onClose();
    } catch (e) {
      setError(String((e as Error).message || e));
      setBusy(false);
    }
  };
  return (
    <section className="note keep-box" aria-label="Keep this dashboard">
      <h3 style={{ margin: 0 }}>Keep this dashboard in the model</h3>
      {error && <p className="lvl-error">{error}</p>}
      {!x && !error && <Loading what="Working out its dashboards: entry" />}
      {x && (
        <>
          <p className="muted small">{x.title}: written to the model's YAML under dashboards: when you Accept, for everyone who opens this page.</p>
          {x.edit?.diff && (
            <pre className="diff">{String(x.edit.diff).split("\n").map((l: string, i: number) => (
              <div key={i} className={l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : "muted"}>{l}</div>))}</pre>
          )}
          <span style={{ display: "flex", gap: "var(--sp-2)" }}>
            <Button className="primary" disabled={busy} onClick={() => answer("accept")}>Accept</Button>
            <Button disabled={busy} onClick={() => answer("dismiss")}>Dismiss</Button>
          </span>
        </>
      )}
      {(error || !x) && <Button variant="ghost" onClick={onClose}>Close</Button>}
    </section>
  );
}

/** A panel's buttons while the dashboard is edited: move it, edit it (a query or a diagram), remove it. */
function EditTools({ def, onEdit, onRemove, onMove }: { def: PanelDef; onEdit?: () => void; onRemove: () => void; onMove: (by: -1 | 1) => void }) {
  const t = def.title || def.panel;
  return (
    <span style={{ display: "flex", gap: "var(--sp-0)" }}>
      <Button variant="ghost" onClick={() => onMove(-1)} title="Move earlier" aria-label={`Move ${t} earlier`}>←</Button>
      <Button variant="ghost" onClick={() => onMove(1)} title="Move later" aria-label={`Move ${t} later`}>→</Button>
      {onEdit ? <Button variant="ghost" onClick={onEdit}>Edit</Button>
        : <span className="muted small" title="Its parameters are edited in the model's YAML for now">{def.panel}</span>}
      <Button variant="ghost" onClick={onRemove} aria-label={`Remove ${t}`}>Remove</Button>
    </span>
  );
}
