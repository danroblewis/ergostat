import { useEffect, useState } from "react";
import { PanelView } from "../charts";
import { PanelBox, normalizePanel } from "../panels";
import { useApi } from "../../hooks/useApi";
import { useTime } from "../../state/time";
import { encodeQuery, type Answer, type Panel, type Query } from "../../lib/query";

/* A panel as it would draw, always: asked again on its own a moment (WAIT) after the last change, so typing asks
   nothing until it pauses; the answer asked before is dropped, and its request cancelled, when a newer one is asked
   (lib/api.ts). A query whose text is still empty is not asked. What a shortcut asked (its ``compiled`` SQL or PromQL)
   is shown under the panel, so it is plainly just SQL or PromQL. */
export const WAIT = 400;   // ms after the last change

function useSettled<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  const key = JSON.stringify(value);
  useEffect(() => {
    const t = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ms]);
  return settled;
}

const written = (q: Query) => q.source === "sql" || q.source === "promql" || q.source === "ergostat";

export function LivePreview({ panel }: { panel: Panel }) {
  const settled = useSettled(panel, WAIT);
  const shown: Panel = { ...settled, id: `${settled.id}-preview`, size: "full" };
  return (
    <section className="qe-preview" aria-label="The panel as it will draw">
      {shown.form === "diagram"
        ? <PanelBox def={normalizePanel({ ...shown, queries: [], diagram: { view: "dynamics", ...(shown.diagram || {}) } })} />
        : <QueryPreview panel={shown} pending={JSON.stringify(panel) !== JSON.stringify(settled)} />}
    </section>
  );
}

function QueryPreview({ panel, pending }: { panel: Panel; pending: boolean }) {
  const { seconds, at } = useTime();
  const asked = panel.queries.filter((q) => !written(q) || (q.text || "").trim());
  const q = asked.length ? encodeQuery({ since: seconds, until: at, points: 120,
    queries: asked.map((x, n) => ({ ...x, label: undefined, hidden: undefined, id: x.id ?? String(n) })) }) : null;
  const got = useApi<Answer>(q ? "query" : null, { q }, { window: false });
  const compiled = (got.data?.results || []).flatMap((r) => (r.compiled || []).map((c: { source: string; text: string }) => ({ id: r.id, ...c })));
  if (!q) return <p className="muted qe-preview-empty">{panel.queries.length ? "Write a query to see it drawn here." : "Add a query to see it drawn here."}</p>;
  const busy = pending || got.loading;
  return (
    <>
      <p className="qe-preview-state muted small" role="status" aria-live="polite">{busy ? "Updating…" : "Up to date"}</p>
      <div className="panel-grid"><PanelView panel={panel} results={got.data?.results} loading={got.loading} error={got.error} /></div>
      {compiled.length > 0 && (
        <div className="pe-compiled">
          <p className="muted small qe-flush">What the shortcuts asked (the same text can be asked of the source itself):</p>
          {compiled.map((c, i) => (
            <p key={i} className="qe-flush"><span className="muted small">{c.id} · {c.source}</span><br />
              <code className="qe-compiled-text">{c.text}</code></p>
          ))}
        </div>
      )}
    </>
  );
}
