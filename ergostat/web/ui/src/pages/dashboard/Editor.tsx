import { useEffect, useMemo, useState } from "react";
import { Button, ErrorNote, PanelView, Select } from "../../components";
import { useApi } from "../../hooks/useApi";
import { apiGet } from "../../lib/api";
import { useTime } from "../../state/time";
import { encodeQuery, type Answer, type Panel, type Query } from "../../lib/query";
import { useStatus } from "../../state/status";
import { PanelBox, normalizePanel } from "../../components/panels";

/* The panel editor (panel-editor.js, in part): a panel's title, note, form and size, and its queries. ergostat has two
   data sources, promql (every metric) and sql (all item data), and /api/query/fields lists exactly those two under
   datasources, each saying whether it can be asked now and, when not, why: an unavailable one is shown, disabled, with
   that reason. A query is written in its source's language, or made from one of the shortcuts that write it (item
   fields, moves, items per state and events write SQL; a metric series writes PromQL); a shortcut's answer says what
   it asked (``compiled``), shown under the preview, so it is plainly just SQL or PromQL. A preview asks the query as
   it stands. A diagram panel has no queries: it names a view, and the system, item or kind drawn. */

/* Each shortcut, the source it writes its query for, and its words. */
const SHORTCUTS: [string, string, string][] = [["items", "sql", "Item fields"], ["moves", "sql", "Item moves"],
  ["counts", "sql", "Items per state"], ["events", "sql", "Events"], ["series", "promql", "Metric series"]];
const sourceOf = (q: Query): string => SHORTCUTS.find(([k]) => k === q.source)?.[1] ?? (q.source === "ergostat" ? "promql" : q.source);
const FORMS: [string, string][] = [["line", "Line"], ["area", "Area"], ["stacked", "Stacked area"], ["step", "Step"], ["bar", "Bar"], ["stat", "Stat"], ["table", "Table"], ["diagram", "Diagram"]];
const VIEWS: [string, string][] = [["dynamics", "Dynamics (stocks and flows)"], ["blocks", "Blocks (the control system)"], ["process", "Process (how items moved)"]];
const SIZES: [string, string][] = [["s", "Small (a third)"], ["m", "Medium (half)"], ["l", "Large (two thirds)"], ["full", "Full width"]];
const AGGS = ["count", "sum", "avg", "min", "max", "last", "p50", "p90", "p95", "p99"];
const TRANSFORMS: [string, string][] = [["none", "None"], ["rate", "Rate"], ["delta", "Change per step"], ["cumulative", "Running total"], ["moving_avg", "Moving average"]];
const MEASURES: [string, string][] = [["entries", "Entries"], ["exits", "Exits"], ["time_in_state", "Time in state"]];

interface DataSource { name: string; type: string; language: string; available: boolean; reason?: string }

export function Editor({ panel, onSave, onCancel }: { panel: Panel; onSave: (p: Panel) => void; onCancel: () => void }) {
  const [p, setP] = useState<Panel>(() => JSON.parse(JSON.stringify(panel)));
  const fields = useApi<any>("query/fields", {}, { window: false });
  const listed: DataSource[] | undefined = fields.data?.datasources;
  const [preview, setPreview] = useState<Panel | null>(null);

  const set = (patch: Partial<Panel>) => setP((x) => ({ ...x, ...patch }));
  const isDiagram = p.form === "diagram";
  const setQuery = (i: number, q: Query) => set({ queries: p.queries.map((x, n) => (n === i ? q : x)) });
  const addQuery = () => {
    const id = "abcdefghijkl"[p.queries.length] || `q${p.queries.length}`;
    const first = listed?.find((d) => d.available);
    set({ queries: [...p.queries, first ? { id, source: first.name, text: "" } : { id, source: "series", agg: "last", transform: "none" }] });
  };

  // exactly the two sources the server lists, an unavailable one disabled with its reason
  const sourceOptions = useMemo(() => (listed || []).map((d) => ({
    value: d.name, label: d.available ? `${d.name} (${d.language})` : `${d.name} (${d.language}): unavailable`,
    disabled: !d.available, title: d.reason,
  })), [listed]);
  const unavailable = (listed || []).filter((d) => !d.available);

  return (
    <div className="pe-overlay" role="dialog" aria-modal="true" aria-label="Edit panel"
      style={{ position: "fixed", inset: 0, zIndex: 50, background: "rgba(0,0,0,.35)", display: "flex", alignItems: "flex-start", justifyContent: "center", overflow: "auto", padding: "3vh 1rem" }}
      onKeyDown={(e) => { if (e.key === "Escape") onCancel(); }}>
      <div className="dash-editor" style={{ background: "var(--bg)", color: "var(--ink)", borderRadius: "var(--radius-menu)", border: "var(--hair) solid var(--line)", padding: "var(--sp-4)", width: "min(1000px, 100%)", display: "grid", gap: "var(--sp-3)" }}>
        <h2 style={{ margin: 0 }}>{panel.title ? "Edit panel" : "Add panel"}</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))", gap: "var(--sp-2) var(--sp-3)" }}>
          <label>Title<br /><input value={p.title} onChange={(e) => set({ title: e.target.value })} style={{ width: "100%" }} autoFocus /></label>
          <label>Note<br /><input value={p.note || ""} onChange={(e) => set({ note: e.target.value })} style={{ width: "100%" }} /></label>
          <label>Chart<br /><Select value={p.form} onChange={(e) => set({ form: e.target.value })} options={FORMS.map(([value, label]) => ({ value, label }))} /></label>
          <label>Size<br /><Select value={p.size || "m"} onChange={(e) => set({ size: e.target.value as Panel["size"] })} options={SIZES.map(([value, label]) => ({ value, label }))} /></label>
          {!isDiagram && <label>Unit<br /><input value={p.display?.unit ?? ""} onChange={(e) => set({ display: { ...(p.display || {}), unit: e.target.value } })} placeholder="from the answer" /></label>}
        </div>
        <ErrorNote error={fields.error} />
        {isDiagram ? <DiagramFields p={p} set={set} /> : (
          <>
            {unavailable.map((d) => (
              <p key={d.name} className="note" role="status">
                <strong>{d.name} ({d.language}) is unavailable here.</strong> {d.reason}
              </p>
            ))}
            <h3 style={{ margin: 0 }}>Queries</h3>
            {p.queries.map((q, i) => (
              <QueryRow key={i} q={q} fields={fields.data} sources={sourceOptions} listed={listed || []}
                onChange={(x) => setQuery(i, x)} onRemove={() => set({ queries: p.queries.filter((_, n) => n !== i) })} />
            ))}
            <div><Button onClick={addQuery} disabled={p.queries.length >= 12}>Add query</Button></div>
          </>
        )}
        <div>
          <Button onClick={() => setPreview({ ...p, id: `${p.id}-preview` })}>Preview</Button>
          {preview && <div className="panel-grid" style={{ marginTop: "var(--sp-2)" }}><PreviewPanel panel={{ ...preview, size: "full" }} /></div>}
        </div>
        <div style={{ display: "flex", gap: "var(--sp-2)", justifyContent: "flex-end" }}>
          <Button onClick={onCancel}>Cancel</Button>
          <Button className="primary" onClick={() => onSave(saved(p))} disabled={!isDiagram && !p.queries.length}>Save panel</Button>
        </div>
      </div>
    </div>
  );
}

/** A panel as saved: titled, and only what its form reads (a diagram keeps no queries, a chart no diagram). */
function saved(p: Panel): Panel {
  const title = p.title.trim() || (p.form === "diagram" ? "Diagram" : "Untitled");
  if (p.form === "diagram") return { ...p, title, queries: [], diagram: { view: "dynamics", ...(p.diagram || {}) } };
  const { diagram: _d, ...rest } = p;
  return { ...rest, title };
}

/** A diagram panel's own fields: the view, and what is drawn (a system, or what an item or a kind passed through). */
function DiagramFields({ p, set }: { p: Panel; set: (patch: Partial<Panel>) => void }) {
  const { status } = useStatus();
  const d = p.diagram || {};
  const put = (patch: Partial<NonNullable<Panel["diagram"]>>) => set({ diagram: { ...d, ...patch } });
  const systems: string[] = status?.systems || [];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))", gap: "var(--sp-2) var(--sp-3)" }}>
      <label>View<br /><Select aria-label="View" value={d.view || "dynamics"} onChange={(e) => put({ view: e.target.value as "dynamics" })}
        options={VIEWS.map(([value, label]) => ({ value, label }))} /></label>
      <label>System<br /><Select aria-label="System" value={d.system || ""} onChange={(e) => put({ system: e.target.value })}
        options={[{ value: "", label: "Everything" }, ...systems.map((x) => ({ value: x, label: x }))]} /></label>
      <label>Only what an item passed through<br /><input value={d.item || ""} onChange={(e) => put({ item: e.target.value })} placeholder="an item's id" /></label>
      <label>Only what a kind touches<br /><input value={d.kind || ""} onChange={(e) => put({ kind: e.target.value })} placeholder="a kind's name" /></label>
    </div>
  );
}

function PreviewPanel({ panel }: { panel: Panel }) {
  if (panel.form === "diagram") return <PanelBox def={normalizePanel(saved(panel))} />;
  return <QueryPreview panel={panel} />;
}

function QueryPreview({ panel }: { panel: Panel }) {
  const { seconds, at } = useTime();
  const q = encodeQuery({ since: seconds, until: at, points: 120, queries: panel.queries.map((x, n) => ({ ...x, label: undefined, hidden: undefined, id: x.id ?? String(n) })) });
  const got = useApi<Answer>("query", { q }, { window: false });
  const asked = (got.data?.results || []).flatMap((r) => (r.compiled || []).map((c: { source: string; text: string }) => ({ id: r.id, ...c })));
  return (
    <>
      <PanelView panel={panel} results={got.data?.results} loading={got.loading} />
      {asked.length > 0 && (
        <div className="pe-compiled" style={{ gridColumn: "1 / -1" }}>
          <p className="muted small" style={{ margin: 0 }}>What the shortcuts asked (the same text can be asked of the source itself):</p>
          {asked.map((c, i) => (
            <p key={i} style={{ margin: 0 }}><span className="muted small">{c.id} · {c.source}</span><br />
              <code style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{c.text}</code></p>
          ))}
        </div>
      )}
    </>
  );
}

function QueryRow({ q, fields, sources, listed, onChange, onRemove }: {
  q: Query; fields: any; sources: { value: string; label: string; disabled?: boolean; title?: string }[]; listed: DataSource[];
  onChange: (q: Query) => void; onRemove: () => void;
}) {
  const src = sourceOf(q);
  const shortcut = SHORTCUTS.some(([k]) => k === q.source);
  const ds = shortcut ? undefined : listed.find((d) => d.name === src);   // written in the source's own language
  const set = (patch: Record<string, any>) => onChange({ ...q, ...patch });
  const kinds = Object.keys(fields?.sources?.[q.source]?.kinds || fields?.sources?.items?.kinds || {});
  const kind = fields?.sources?.items?.kinds?.[q.kind] || fields?.sources?.[q.source]?.kinds?.[q.kind];
  const states: string[] = kind?.states || [];
  const known = sources.some((s) => s.value === src);
  const opts = known ? sources : [...sources, { value: src, label: `${src} (not offered by this server)` }];
  const shortcuts = [{ value: "", label: `Written in ${listed.find((d) => d.name === src)?.language ?? src}` },
    ...SHORTCUTS.filter(([k, s]) => s === src && fields?.sources?.[k]).map(([k, , label]) => ({ value: k, label }))];
  return (
    <fieldset className="pe-query" style={{ border: "var(--hair) solid var(--line)", borderRadius: "var(--radius)", padding: "var(--sp-2)", display: "grid", gap: "var(--sp-2)" }}>
      <legend>Query {q.id}</legend>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-2)", alignItems: "end" }}>
        <label>Source<br />
          <Select value={src} aria-label="Source" options={opts} onChange={(e) => {
            onChange({ id: q.id, label: q.label, source: e.target.value, text: q.text ?? "" });
          }} />
        </label>
        <label>Query<br />
          <Select value={ds ? "" : q.source} aria-label="Query" options={shortcuts} onChange={(e) => {
            const k = e.target.value;
            onChange(!k ? { id: q.id, label: q.label, source: src, text: q.text ?? "" } : { id: q.id, label: q.label, source: k, agg: k === "series" ? "last" : "count", transform: "none" });
          }} />
        </label>
        <label>Label<br /><input value={q.label || ""} onChange={(e) => set({ label: e.target.value || undefined })} /></label>
        {!ds && ["items", "moves", "counts"].includes(q.source) && (
          <label>Kind<br /><Select value={q.kind || ""} onChange={(e) => set({ kind: e.target.value, state: undefined, field: undefined })}
            options={[{ value: "", label: "Choose…" }, ...kinds.map((k) => ({ value: k, label: k }))]} /></label>
        )}
        {q.source === "items" && (
          <label>Field<br /><Select value={q.field || ""} onChange={(e) => set({ field: e.target.value })}
            options={[{ value: "", label: "Choose…" }, ...(kind?.fields || []).map((f: any) => ({ value: f.name, label: f.name }))]} /></label>
        )}
        {q.source === "moves" && (
          <label>Measure<br /><Select value={q.measure || "entries"} onChange={(e) => set({ measure: e.target.value })} options={MEASURES.map(([value, label]) => ({ value, label }))} /></label>
        )}
        {(q.source === "moves" || q.source === "counts") && states.length > 0 && (
          <label>States<br />
            <select multiple size={Math.min(5, states.length)} value={q.state || []} onChange={(e) => set({ state: [...e.target.selectedOptions].map((o) => o.value) })}>
              {states.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        )}
        {q.source === "series" && (
          <label>Series<br /><Select value={q.series || ""} onChange={(e) => set({ series: e.target.value })}
            options={[{ value: "", label: "Choose…" }, ...(fields?.sources?.series?.series || []).map((s: any) => ({ value: s.name, label: s.name }))]} /></label>
        )}
        {q.source === "events" && (
          <label>Event type<br /><Select value={q.type || ""} onChange={(e) => set({ type: e.target.value })}
            options={[{ value: "", label: "Any" }, ...(fields?.sources?.events?.types || []).map((t: string) => ({ value: t, label: t }))]} /></label>
        )}
        {!ds && (
          <>
            <label>Aggregate<br /><Select value={q.agg || "count"} onChange={(e) => set({ agg: e.target.value })} options={AGGS} /></label>
            <label>Transform<br /><Select value={q.transform || "none"} onChange={(e) => set({ transform: e.target.value, ...(e.target.value === "rate" ? { rate_per: q.rate_per || "hour" } : {}) })}
              options={TRANSFORMS.map(([value, label]) => ({ value, label }))} /></label>
          </>
        )}
        <Button variant="ghost" onClick={onRemove}>Remove query</Button>
      </div>
      {ds && <TextQuery source={ds} text={q.text || ""} onChange={(text) => set({ text })} />}
    </fieldset>
  );
}

/* A query in its source's own language; for a PromQL source, the metric names the source knows are suggested as the
   word at the end is typed (/api/query/suggest, what=metrics). */
function TextQuery({ source, text, onChange }: { source: DataSource; text: string; onChange: (t: string) => void }) {
  const promql = /promql/i.test(source.language);
  const word = promql ? (/([A-Za-z_:][A-Za-z0-9_:]*)$/.exec(text)?.[1] ?? "") : "";
  const [picks, setPicks] = useState<string[]>([]);
  useEffect(() => {
    if (!promql || !word) { setPicks([]); return; }
    const ctl = new AbortController();
    const t = setTimeout(() => {
      apiGet<any>("query/suggest", { source: source.name, what: "metrics", prefix: word, metric: "", label: "" }, ctl.signal)
        .then((got) => setPicks((got.suggestions || []).map((s: any) => (typeof s === "string" ? s : s.name)).filter((n: string) => n !== word).slice(0, 12)))
        .catch(() => setPicks([]));
    }, 200);
    return () => { clearTimeout(t); ctl.abort(); };
  }, [promql, word, source.name]);
  return (
    <div>
      <label>{source.language} <span className="muted small">({source.name})</span><br />
        <textarea className="pe-text" value={text} spellCheck={false} rows={4} onChange={(e) => onChange(e.target.value)}
          style={{ width: "100%", fontFamily: "var(--mono, ui-monospace, monospace)", boxSizing: "border-box" }}
          placeholder={promql ? 'rate(http_requests_total[5m])   ·   {__name__=~".+"} lists every metric' : `a ${source.language} query`} />
      </label>
      {picks.length > 0 && (
        <ul role="listbox" aria-label="Suggestions" style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-1)", listStyle: "none", margin: 0, padding: 0 }}>
          {picks.map((n) => (
            <li key={n}><Button variant="ghost" onClick={() => onChange(text.slice(0, text.length - word.length) + n)}><code>{n}</code></Button></li>
          ))}
        </ul>
      )}
    </div>
  );
}
