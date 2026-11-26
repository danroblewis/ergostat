import { useEffect, useState } from "react";
import { Button, ErrorNote, Loading, Note, Page, Select } from "../../components";
import { DashboardPanel } from "./DashboardPanel";
import { apiGet } from "../../lib/api";
import { useStatus } from "../../state/status";
import { defaultDashboard, MOST, queuesOf } from "./lib/defaults";
import { type Dashboard, type Panel } from "../../lib/query";
import { Editor } from "./Editor";

/* The Dashboard (dashboard.js pageDashboard): a grid of panels, kept in this browser and never written to the server.
   With none kept, the default is built from what the record holds. Each panel is a component any page can show: a
   QueryPanel asking for its own answer on the refresh chosen, or a DiagramPanel drawing the diagram it names (loaded
   only when one is on the dashboard: it brings ELK). */

const EVERY: Record<string, number> = { Off: 0, "10s": 10000, "30s": 30000, "1m": 60000, "5m": 300000 };
const keyOf = (name: string) => `ergostat.dashboard.${name}`;

function stored(name: string): Dashboard | null {
  try {
    const d = JSON.parse(localStorage.getItem(keyOf(name)) || "null");
    return d && Array.isArray(d.panels) ? d : null;
  } catch { return null; }
}
function store(name: string, d: Dashboard | null): void {
  try { if (d) localStorage.setItem(keyOf(name), JSON.stringify(d)); else localStorage.removeItem(keyOf(name)); } catch { /* kept for this visit only */ }
}

export default function DashboardPage() {
  const { status } = useStatus();
  const name = status?.name;
  const [d, setD] = useState<Dashboard | null>(null);
  const [failed, setFailed] = useState<Error | null>(null);
  const [editing, setEditing] = useState(false);
  const [open, setOpen] = useState<Panel | null>(null);
  const [every, setEvery] = useState("30s");

  useEffect(() => {
    if (name == null || d) return;
    const kept = stored(name);
    if (kept) { setD(kept); return; }
    let gone = false;
    (async () => {
      const fields = await apiGet("query/fields");
      const infos = (await apiGet("items", { n: 1, eta: 0 }).catch(() => null))?.kinds || [];
      if (!gone) setD(defaultDashboard(fields, infos, queuesOf(fields, infos)));
    })().catch((e) => { if (!gone) setFailed(e); });
    return () => { gone = true; };
  }, [name, d]);

  const change = (next: Dashboard) => { setD(next); if (name != null) store(name, next); };
  const panels = d?.panels || [];

  const [refreshed, setRefreshed] = useState(0);

  const save = (p: Panel) => {
    if (!d) return;
    const has = d.panels.some((x) => x.id === p.id);
    change({ ...d, panels: has ? d.panels.map((x) => (x.id === p.id ? p : x)) : [...d.panels, p] });
    setOpen(null);
  };
  const remove = (id: string) => d && change({ ...d, panels: d.panels.filter((x) => x.id !== id) });
  const move = (id: string, by: -1 | 1) => {
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
      <label className="muted small">Refresh <Select value={every} onChange={(e) => setEvery(e.target.value)} options={Object.keys(EVERY)} /></label>
      <Button onClick={() => setRefreshed((n) => n + 1)}>Refresh now</Button>
      {editing && <Button onClick={() => setOpen(fresh())} disabled={panels.length >= MOST}>Add panel</Button>}
      {editing && d && name != null && (
        <Button onClick={() => { store(name, null); setD(null); }} title="Forget this browser's dashboard and build the default again">Reset to default</Button>
      )}
      <Button className={`dash-edit${editing ? " on" : ""}`} aria-pressed={editing} onClick={() => setEditing(!editing)}>{editing ? "Done" : "Edit"}</Button>
    </span>
  );

  return (
    <Page title={d?.title || "Dashboard"} actions={actions} className="dash">
      <ErrorNote error={failed} />
      {!d && !failed && <Loading />}
      {d && !panels.length && <Note>No panels. Choose Edit, then Add panel.</Note>}
      <div className="panel-grid">
        {panels.map((p) => (
          <DashboardPanel key={p.id} panel={p} every={EVERY[every] || null} refreshKey={refreshed}
            tools={editing && <EditTools panel={p} onEdit={() => setOpen(p)} onRemove={() => remove(p.id)} onMove={(by) => move(p.id, by)} />} />
        ))}
      </div>
      {open && <Editor panel={open} onSave={save} onCancel={() => setOpen(null)} />}
    </Page>
  );
}

/** A panel's buttons while the dashboard is edited: move it, edit it, remove it. */
function EditTools({ panel, onEdit, onRemove, onMove }: { panel: Panel; onEdit: () => void; onRemove: () => void; onMove: (by: -1 | 1) => void }) {
  return (
    <span style={{ display: "flex", gap: "var(--sp-0)" }}>
      <Button variant="ghost" onClick={() => onMove(-1)} title="Move earlier" aria-label={`Move ${panel.title} earlier`}>←</Button>
      <Button variant="ghost" onClick={() => onMove(1)} title="Move later" aria-label={`Move ${panel.title} later`}>→</Button>
      <Button variant="ghost" onClick={onEdit}>Edit</Button>
      <Button variant="ghost" onClick={onRemove} aria-label={`Remove ${panel.title}`}>Remove</Button>
    </span>
  );
}
