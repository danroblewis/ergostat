import { useState, type ReactNode } from "react";
import { useApi } from "../../../hooks/useApi";
import { diagramOf } from "../../../lib/hrefs";
import type { Panel } from "../../../lib/query";
import { Button, Check, ErrorNote, Select } from "../../ui";
import { asQueryPanel, KINDS } from "../kinds/index";
import { normalizePanel } from "../normalize";
import type { PanelDef } from "../types";
import { Editor, EditorFrame, SIZES } from "./Editor";

/* A panel's settings, whatever its kind: a chart of queries or a diagram in the query editor (Editor.tsx); any other
   kind its words, its size, and the parameters its kind takes, as the model checks them (GET /api/panel-kinds, from
   spec/dashboards.py KINDS): text, a number, a flag, a list (comma-separated, as the address writes it) or one of its
   words. A parameter written `$projection`, `$item` or `$agent` is taken from the page's address. */

type Param = { type: "text" | "number" | "flag" | "list" | "choice" | "data"; words?: string[]; many?: boolean };
type Kinds = Record<string, { needs: string | null; params: Record<string, Param> }>;

/** A panel as the query editor edits it (the query engine's Panel; a diagram as form "diagram"). */
const forEditor = (def: PanelDef): Panel =>
  def.panel === "diagram" ? { ...asQueryPanel(def), form: "diagram", diagram: diagramOf(def.address || "/diagram") } : asQueryPanel(def);
const QUERY = new Set(["query", "diagram"]);

export function PanelEditor({ def, adding, onSave, onCancel }: {
  def: PanelDef; adding?: boolean; onSave: (d: PanelDef) => void; onCancel: () => void;
}) {
  const [kind, setKind] = useState(def.panel || "query");
  const picked = kind === def.panel || (QUERY.has(kind) && QUERY.has(def.panel)) ? def : { id: def.id, panel: kind, title: def.title, size: def.size };
  const picker = (
    <label>Panel<br /><Select aria-label="Panel" value={QUERY.has(kind) ? "query" : kind} onChange={(e) => setKind(e.target.value)}
      options={[{ value: "query", label: "A chart of queries, or a diagram" },
        ...Object.entries(KINDS).filter(([k]) => !QUERY.has(k)).map(([k, x]) => ({ value: k, label: x.label }))]} /></label>
  );
  if (QUERY.has(kind)) {
    return <Editor key="query" panel={forEditor(picked)} adding={adding} kindPicker={picker} onCancel={onCancel}
      onSave={(x) => onSave({ ...normalizePanel(x), id: def.id, fit: def.fit, quiet: def.quiet })} />;
  }
  return <KindEditor key={kind} def={picked} adding={adding} picker={picker} onSave={onSave} onCancel={onCancel} />;
}

const asText = (v: unknown) => (v == null ? "" : Array.isArray(v) ? v.join(", ") : String(v));

function KindEditor({ def, adding, picker, onSave, onCancel }: {
  def: PanelDef; adding?: boolean; picker: ReactNode; onSave: (d: PanelDef) => void; onCancel: () => void;
}) {
  const kinds = useApi<Kinds>("panel-kinds", {}, { window: false });
  const [d, setD] = useState<PanelDef>(() => ({ ...def }));
  const set = (k: string, v: unknown) => setD((x) => {
    const n = { ...x, [k]: v };
    if (v === undefined || v === "") delete n[k];
    return n;
  });
  const kind = kinds.data?.[d.panel];
  const params = Object.entries(kind?.params || {}).filter(([, p]) => p.type !== "data");
  const needs = kind?.needs;
  const missing = !!needs && (d[needs] == null || d[needs] === "");
  const typed = (k: string, p: Param, raw: string): unknown => {
    if (raw.trim() === "") return undefined;
    if (p.type === "number") return Number.isFinite(+raw) ? +raw : raw;
    if (p.type === "list" || (p.type === "choice" && p.many)) {
      return Array.isArray(def[k]) ? raw.split(",").map((x) => x.trim()).filter(Boolean) : raw;
    }
    return raw;
  };
  return (
    <EditorFrame heading={adding ? "Add panel" : "Edit panel"} onCancel={onCancel}>
      {picker}
      <div className="pe-fields">
        <label>Title<br /><input value={d.title || ""} onChange={(e) => set("title", e.target.value)} autoFocus /></label>
        <label>Note<br /><input value={d.note || ""} onChange={(e) => set("note", e.target.value)} /></label>
        <label>Size<br /><Select value={d.size || "m"} onChange={(e) => set("size", e.target.value)}
          options={SIZES.map(([value, label]) => ({ value, label }))} /></label>
        <Check label="Tall" checked={!!d.tall} onChange={(e) => set("tall", e.target.checked || undefined)} />
        <Check label="As tall as what it shows" checked={!!d.fit} onChange={(e) => set("fit", e.target.checked || undefined)} />
        <Check label="Not drawn while it has nothing to say" checked={!!d.quiet} onChange={(e) => set("quiet", e.target.checked || undefined)} />
      </div>
      <ErrorNote error={kinds.error} />
      {params.length > 0 && (
        <div className="pe-fields">
          {params.map(([k, p]) => {
            const label = <>{k}{k === needs ? " (needed)" : ""}</>;
            if (p.type === "flag") return <Check key={k} label={label} checked={d[k] === true} onChange={(e) => set(k, e.target.checked || undefined)} />;
            if (p.type === "choice" && !p.many) {
              return <label key={k}>{label}<br /><Select aria-label={k} value={asText(d[k])} onChange={(e) => set(k, e.target.value || undefined)}
                options={[{ value: "", label: "(as the panel chooses)" }, ...(p.words || [])]} /></label>;
            }
            return (
              <label key={k}>{label}<br />
                <input aria-label={k} value={asText(d[k])} type={p.type === "number" ? "number" : "text"}
                  placeholder={p.words ? p.words.join(", ") : p.type === "list" ? "names, comma-separated" : k === "projection" || k === "item" || k === "agent" ? `$${k}: this page's` : ""}
                  onChange={(e) => set(k, typed(k, p, e.target.value))} />
              </label>
            );
          })}
        </div>
      )}
      <div style={{ display: "flex", gap: "var(--sp-2)", justifyContent: "flex-end" }}>
        <Button onClick={onCancel}>Cancel</Button>
        <Button className="primary" disabled={missing} title={missing ? `A ${d.panel} panel needs ${needs}` : undefined}
          onClick={() => onSave(d)}>Save panel</Button>
      </div>
    </EditorFrame>
  );
}
