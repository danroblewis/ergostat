import { useState, type ReactNode } from "react";
import { apiSend, isPublic } from "../../lib/api";
import { useDashboards } from "../../state/dashboards";
import { Button, ErrorNote, Note } from "../ui";
import { DashboardView } from "./DashboardView";
import { PanelEditor } from "./editor/PanelEditor";
import type { DashboardDef, PanelDef } from "./types";

/* Every page that is a dashboard is edited where it is drawn (SPEC §4f, *Editing in place*): Edit, then move, remove,
   add a panel and edit its settings; Save writes it into the model's YAML where it belongs, at once (the owner saving
   is the owner accepting: POST /api/dashboards/save, numbers/display.py save); Cancel forgets the edit; Reset to
   ergostat's takes a saved one out (POST /api/dashboards/reset), so ergostat's own is drawn there again.

   Where it is saved (``target``): a projection's own list or show ({projection, role}: under the projection's
   `dashboards:`, in the file it is defined in), or a dashboard under `dashboards:` by its name (a declared one where it
   is; ergostat's Goals, Agents and Record pages as `goals`, `agents`, `record`; an agent's page as the `page: agent`
   dashboard; a new one, named when it is saved, with `nav: true`). */

export type SaveTarget =
  | { projection: string; role: "list" | "show" }
  | { name: string; page?: string | null; nav?: string | boolean | null; new?: boolean };

const NAME = /^[a-z][a-z0-9-]{0,63}$/;

/** A panel's `$WORD`s filled in from the address's words (`bind`), as the page draws it. */
export function filled(d: PanelDef, bind: Record<string, string> = {}): PanelDef {
  const fill = (v: unknown) => (typeof v === "string" && v.startsWith("$") && bind[v.slice(1)] != null ? bind[v.slice(1)] : v);
  return Object.fromEntries(Object.entries(d).map(([k, v]) => [k, fill(v)])) as PanelDef;
}

/** A panel as it is saved: its declaration alone (the page's id, its handlers and what it chose are the page's). */
const plainOf = (d: PanelDef) => Object.fromEntries(Object.entries(d)
  .filter(([k, v]) => k !== "id" && k !== "selected" && typeof v !== "function" && v !== undefined)) as PanelDef;

const withIds = (ps: PanelDef[]) => {
  const seen = new Set<string>();
  return ps.map((d, i) => {
    let id = d.id || `p${i + 1}`;
    while (seen.has(id)) id = `${id}-${i + 1}`;
    seen.add(id);
    return { ...d, id };
  });
};

export type Editing = {
  editing: boolean;
  /** the panels to draw: the edit while editing, else the dashboard's, each `$WORD` filled from the address */
  panels: PanelDef[];
  /** the Edit control, or while editing the editing bar (Add panel, Save, Cancel, Reset to ergostat's) */
  bar: ReactNode;
  /** a panel's own buttons while editing (move, edit, remove), by its id */
  tools: (def: PanelDef) => ReactNode;
  /** the panel editor, when a panel is being edited or added */
  dialog: ReactNode;
};

/** Editing a dashboard where it is drawn. `base`: what is drawn when nothing is being edited (its panels as declared,
 *  `$WORD`s and all); `saved`: it is the model's own, and ergostat has a page of its own there (so it can be reset);
 *  `start`: editing from the first (a new dashboard); `onDone`: after a save or a reset, with the name it was saved
 *  under. With no `target` (or on a public, read-only name) nothing is editable. */
export function useEditing({ base, target, saved = false, bind, start = false, onDone, onCancel }: {
  base: DashboardDef | null; target: SaveTarget | null; saved?: boolean; bind?: Record<string, string>; start?: boolean;
  onDone?: (name: string, reset: boolean) => void; onCancel?: () => void;
}): Editing {
  const { refresh } = useDashboards();
  const [draft, setDraft] = useState<PanelDef[] | null>(start ? [] : null);
  const [open, setOpen] = useState<{ def: PanelDef; adding: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const editable = !!target && !isPublic();
  const editing = editable && draft != null;
  const shown = editing ? draft! : withIds(base?.panels || []);
  const isNew = !!target && "name" in target && !!target.new;

  const begin = () => { setDraft(withIds((base?.panels || []).map((d) => ({ ...d })))); setError(null); };
  const cancel = () => { setDraft(null); setOpen(null); setError(null); onCancel?.(); };
  const change = (f: (ps: PanelDef[]) => PanelDef[]) => setDraft((ps) => (ps ? f(ps) : ps));
  const move = (id: string | undefined, by: -1 | 1) => change((ps) => {
    const list = [...ps], i = list.findIndex((x) => x.id === id), j = i + by;
    if (i < 0 || j < 0 || j >= list.length) return ps;
    [list[i], list[j]] = [list[j], list[i]];
    return list;
  });
  const fresh = (): PanelDef => {
    let n = shown.length + 1;
    while (shown.some((x) => x.id === `p${n}`)) n++;
    return { panel: "query", id: `p${n}`, title: "", size: "m", form: "line", queries: [] };
  };
  const put = (def: PanelDef) => {
    change((ps) => (ps.some((x) => x.id === def.id) ? ps.map((x) => (x.id === def.id ? def : x)) : [...ps, def]));
    setOpen(null);
  };

  const send = async (reset: boolean) => {
    if (!target) return;
    setBusy(true);
    setError(null);
    const where = "name" in target
      ? { name: isNew ? name : target.name, page: target.page ?? undefined, new: isNew || undefined,
          nav: isNew ? true : target.nav === "" ? true : target.nav ?? undefined }
      : { projection: target.projection, role: target.role };
    const body = reset ? where : {
      ...where, title: isNew ? (name.charAt(0).toUpperCase() + name.slice(1)).replace(/-/g, " ") : base?.title || undefined,
      description: base?.description || undefined, since: base?.since ?? undefined, panels: (draft || []).map(plainOf),
    };
    try {
      const got = await apiSend<any>(`dashboards/${reset ? "reset" : "save"}`, body);
      setDraft(null);
      refresh();
      onDone?.(String(got?.dashboard || where.name || ""), reset);
    } catch (e) {
      setError(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  };

  const bar = !editable ? null : !editing ? (
    <Button className="dash-edit" onClick={begin} title="Change this dashboard where it is drawn; Save writes it to the model">Edit</Button>
  ) : (
    <span className="dash-edit-bar" role="toolbar" aria-label="Editing this dashboard">
      <Button onClick={() => setOpen({ def: fresh(), adding: true })} disabled={shown.length >= 24}>Add panel</Button>
      {isNew && <label className="muted small">Name <input aria-label="Its name" value={name} placeholder="its address, /NAME"
        onChange={(e) => setName(e.target.value.toLowerCase())} /></label>}
      <Button className="primary" disabled={busy || !shown.length || (isNew && !NAME.test(name))} onClick={() => send(false)}
        title="Write it to the model's YAML, where it belongs">Save</Button>
      <Button disabled={busy} onClick={cancel}>Cancel</Button>
      {saved && <Button disabled={busy} onClick={() => send(true)}
        title="Take the saved dashboard out of the model's YAML: ergostat's own is drawn here again">Reset to ergostat's</Button>}
    </span>
  );

  const tools = (def: PanelDef) => {
    if (!editing) return null;
    const t = def.title || def.panel;
    return (
      <span className="dash-panel-tools">
        <Button variant="ghost" onClick={() => move(def.id, -1)} title="Move earlier" aria-label={`Move ${t} earlier`}>←</Button>
        <Button variant="ghost" onClick={() => move(def.id, 1)} title="Move later" aria-label={`Move ${t} later`}>→</Button>
        <Button variant="ghost" onClick={() => { const d = draft?.find((x) => x.id === def.id); if (d) setOpen({ def: d, adding: false }); }}
          aria-label={`Edit ${t}`}>Edit</Button>
        <Button variant="ghost" onClick={() => change((ps) => ps.filter((x) => x.id !== def.id))} aria-label={`Remove ${t}`}>Remove</Button>
      </span>
    );
  };

  return {
    editing,
    // while editing, a quiet panel is drawn too, so it can be moved, changed or removed
    panels: shown.map((d) => filled(editing && d.quiet ? { ...d, quiet: undefined } : d, bind)),
    bar: <>{bar}{error && <ErrorNote error={error} />}</>,
    tools,
    dialog: open && <PanelEditor def={open.def} adding={open.adding} onSave={put} onCancel={() => setOpen(null)} />,
  };
}

/** A dashboard drawn where it is, editable there: its panels on the grid, the editing bar given to the page (`head`:
 *  where the page puts it, its heading's actions), a panel's own buttons beside the page's (`tools`). `decorate`
 *  gives a drawn panel what the page hands it (a click, the address's choices); `only` leaves out a panel the page
 *  does not draw now (never while editing). */
export function EditableDashboard({ ed, every, refreshKey, tools, decorate, only, empty }: {
  ed: Editing; every?: number | null; refreshKey?: unknown; tools?: (def: PanelDef) => ReactNode;
  decorate?: (def: PanelDef) => PanelDef; only?: (def: PanelDef) => boolean; empty?: ReactNode;
}) {
  const panels = ed.panels.filter((d) => ed.editing || !only || only(d)).map((d) => (decorate ? decorate(d) : d));
  return (
    <>
      {ed.editing && !panels.length && (empty ?? <Note>No panels yet: Add panel.</Note>)}
      <DashboardView panels={panels} every={every} refreshKey={refreshKey}
        tools={(def) => (ed.editing || tools ? <>{tools?.(def)}{ed.tools(def)}</> : undefined)} />
      {ed.dialog}
    </>
  );
}
