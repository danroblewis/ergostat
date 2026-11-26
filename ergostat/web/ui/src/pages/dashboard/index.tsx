import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, Check, ErrorNote, Loading, Note, Page, Select } from "../../components";
import { asQueryPanel, DashboardView, DeclaredDashboard, EVERY, normalizeDashboard, normalizePanel, Refresh, type DashboardDef, type PanelDef } from "../../components/panels";
import { apiGet, apiPost, apiSend, isPublic } from "../../lib/api";
import { diagramOf } from "../../lib/hrefs";
import type { Panel } from "../../lib/query";
import { PAGES, pageDashboard, type PageName } from "../../lib/pages";
import { dashboardHref, useDashboards } from "../../state/dashboards";
import { useStatus } from "../../state/status";
import { Editor } from "./Editor";
import { store, stored } from "./lib/draft";
import { defaultDashboard, MOST, queuesOf } from "./lib/defaults";

/* The Dashboard: a grid of panels of any kind (components/panels), each asking for its own answer. Two kinds of
   dashboard: this browser's draft (kept here, with none kept the default built from what the record holds), and those
   the model declares under `dashboards:` (SPEC §4f), opened by name (?name=NAME) and drawn as declared. Keep sends the
   draft to the server, which works out its `dashboards:` entry; the owner Accepts it here and the model holds it. */

/** A panel as the editor edits it (the query engine's Panel; a diagram as form "diagram"), and back. */
const forEditor = (def: PanelDef): Panel =>
  def.panel === "diagram" ? { ...asQueryPanel(def), form: "diagram", diagram: diagramOf(def.address || "/diagram") } : asQueryPanel(def);
const EDITABLE = new Set(["query", "diagram"]);

export default function DashboardPage() {
  const [q] = useSearchParams();
  const name = q.get("name");
  return name ? <Declared name={name} /> : <Draft />;
}

/** The pages a draft may start from as a copy: those that show no one thing (an agent's page needs its agent). */
const COPYABLE = (Object.keys(PAGES) as PageName[]).filter((k) => !PAGES[k].binds);

/** Which dashboard: this browser's draft, one the model declares, or a copy of one of ergostat's own pages to start
 *  the draft from. */
function Chooser({ name, onDraft }: { name: string | null; onDraft?: (d: DashboardDef) => void }) {
  const { list } = useDashboards();
  const { status } = useStatus();
  const navigate = useNavigate();
  const options = [
    { value: "", label: "This browser's draft" },
    ...(list || []).map((d) => ({ value: d.name, label: d.title || d.name })),
    ...COPYABLE.map((k) => ({ value: `copy:${k}`, label: `A copy of the ${PAGES[k].title} page` })),
  ];
  const choose = (v: string) => {
    if (!v.startsWith("copy:")) return navigate(v ? `/dashboard?name=${encodeURIComponent(v)}` : "/dashboard");
    if (status?.name == null || (stored(status.name) && !confirm("Replace this browser's draft with a copy of the page?"))) return;
    const page = v.slice(5) as PageName;
    const d = normalizeDashboard({ ...pageDashboard(page), page });
    store(status.name, d);
    if (onDraft) onDraft(d);              // the draft is on the page already: it is this now
    else navigate("/dashboard?edit=1");
  };
  return (
    <label className="muted small">Dashboard <Select aria-label="Dashboard" value={name || ""} options={options}
      onChange={(e) => choose(e.target.value)} /></label>
  );
}

/** A dashboard the model declares, drawn as declared; Edit a copy makes it this browser's draft (Keep puts it back in
 *  place, under the same name). */
function Declared({ name }: { name: string }) {
  const { status } = useStatus();
  const navigate = useNavigate();
  const copy = (d: DashboardDef) => {
    if (status?.name == null) return;
    store(status.name, { ...d, name: d.name || name });
    navigate("/dashboard?edit=1");
  };
  return (
    <DeclaredDashboard name={name} actions={(d) => (
      <>
        <Chooser name={name} />
        {d?.nav != null && <a className="small" href={dashboardHref(name)}>its own page</a>}
        <Button onClick={() => d && copy(d)} disabled={!d} title="Make a copy of it this browser's draft, to change">Edit a copy</Button>
      </>
    )} />
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
      <Chooser name={null} onDraft={(next) => { setD(next); setEditing(true); }} />
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

/** Where a kept dashboard is shown, besides /dashboard?name=: in the header's navigation (its own address, /d/NAME),
 *  or in the place of one of ergostat's own pages. */
function KeepWhere({ d, onPropose, onClose }: { d: DashboardDef; onPropose: (d: DashboardDef) => void; onClose: () => void }) {
  const [nav, setNav] = useState(d.nav != null);
  const [page, setPage] = useState(d.page || "");
  const binds = page ? PAGES[page as PageName]?.binds : undefined;
  const bound = d.panels.some((x) => Object.values(x).some((v) => typeof v === "string" && v.startsWith("$")));
  return (
    <>
      <p className="muted small">
        {d.name ? <>Kept as dashboard <b>{d.name}</b>, in place of the one declared under that name.</> : <>Kept under its title, {d.title}.</>}
      </p>
      <span style={{ display: "flex", gap: "var(--sp-3)", flexWrap: "wrap", alignItems: "center" }}>
        <Check label="In the navigation, at its own address" checked={nav && !page} disabled={!!page} onChange={(e) => setNav(e.target.checked)} />
        <label className="muted small">In place of <Select aria-label="In place of a page" value={page} onChange={(e) => setPage(e.target.value)}
          options={[{ value: "", label: "no page" }, ...(Object.keys(PAGES) as PageName[]).map((k) => ({ value: k, label: `the ${PAGES[k].title} page` }))]} /></label>
      </span>
      {binds && <p className="muted small">Its panels may write {binds}: ${binds}, taken from the page's address.</p>}
      {bound && !binds && <p className="lvl-error small">A panel takes $agent, $item or $kind from an address: choose the page it is for.</p>}
      <span style={{ display: "flex", gap: "var(--sp-2)" }}>
        <Button className="primary" onClick={() => onPropose({ ...d, nav: nav && !page ? (d.nav || true) as any : null, page: page || null })}>Propose</Button>
        <Button variant="ghost" onClick={onClose}>Close</Button>
      </span>
    </>
  );
}

/** Keep: where it is shown is chosen, then the draft is sent to the server, which works out its `dashboards:` entry and
 *  shows the change; Accept writes it to the model, Dismiss lets it go. Nothing is written before Accept. */
function KeepBox({ d, onClose }: { d: DashboardDef; onClose: () => void }) {
  const navigate = useNavigate();
  const [asked, setAsked] = useState<DashboardDef | null>(null);
  const [x, setX] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!asked) return;
    apiSend("propose", { title: asked.title, since: asked.since ?? undefined, name: asked.name, nav: asked.nav ?? undefined,
      page: asked.page ?? undefined, panels: asked.panels }, { keep: "dashboard" })
      .then(setX).catch((e) => setError(String(e.message || e)));
  }, [asked]);
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
      {!asked && <KeepWhere d={d} onPropose={setAsked} onClose={onClose} />}
      {error && <p className="lvl-error">{error}</p>}
      {asked && !x && !error && <Loading what="Working out its dashboards: entry" />}
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
      {asked && (error || !x) && <Button variant="ghost" onClick={onClose}>Close</Button>}
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
