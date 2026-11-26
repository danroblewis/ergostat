import { useEffect, useMemo, useState } from "react";
import { layoutBlocks, layoutDynamics, layoutProcess, structureKey, type Layout } from "./layout";
import { pmLabel } from "./Process";

export type ViewKey = "dynamics" | "blocks" | "process";

/** /api/graph's answer when it is the view asked for (an answer for the view before is not drawn as this one). */
export function graphOf(view: ViewKey, data: any): any | undefined {
  if (!data?.kind) return undefined;
  const ok = view === "process" ? data.kind === "process" : view === "blocks" ? data.kind === "blocks" : data.kind !== "process" && data.kind !== "blocks";
  return ok ? data : undefined;
}

/** What to say instead of a drawing when there is nothing to draw; null when there is. */
export function emptyText(g: any, view: ViewKey): string | null {
  if (!g || g.nodes.length) return null;
  if (view === "process")
    return (g.kinds || []).length ? `Nothing on the record in the window for ${g.kinds.map((k: any) => k.name).join(", ")}.` : "No kinds of item here: its parts are counted by sensors.";
  return g.subset ? `${g.subset.says}.` : view === "blocks" ? "No control system here: no goal, and no block that acts." : "Nothing to draw: the model is empty.";
}

/** The graph laid out (ELK, off the main thread's way): made again only when its structure changes, so new values
 *  are drawn where the parts already are. ``key`` changes with each new layout. */
export function useDiagramLayout(g: any, view: ViewKey, show = ""): { lay: Layout | null; key: string; error: string | null } {
  const key = useMemo(() => (g ? structureKey(g) + (view === "process" ? JSON.stringify([show, g.nodes.map((n: any) => n.count)]) : "") : ""), [g, view, show]);
  const [laid, setLaid] = useState<{ key: string; lay: Layout } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!g || !key || laid?.key === key) return;
    let gone = false;
    const run = view === "blocks" ? layoutBlocks(g) : view === "process" ? layoutProcess(g, (e) => pmLabel(e, show)) : layoutDynamics(g);
    run.then((lay) => { if (!gone) { setLaid({ key, lay }); setError(null); } })
      .catch((e) => { if (!gone) setError(String(e?.message || e)); });
    return () => { gone = true; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return { lay: laid && g ? laid.lay : null, key: laid?.key ?? "", error };
}

/** The box around everything laid out (and the captions under it), for Fit. */
export function boundsOf(lay: Layout | null): { x: number; y: number; width: number; height: number } | null {
  const xs = lay ? [...lay.children, ...lay.hulls] : [];
  if (!xs.length) return null;
  const x0 = Math.min(...xs.map((c) => c.x)), y0 = Math.min(...xs.map((c) => c.y));
  return { x: x0, y: y0, width: Math.max(...xs.map((c) => c.x + c.width)) - x0, height: Math.max(...xs.map((c) => c.y + c.height + 30)) - y0 };
}
