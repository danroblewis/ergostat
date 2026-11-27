import { useCallback, useEffect, useMemo, useState } from "react";
import { useApi } from "../../hooks/useApi";
import { diagramHref } from "../../lib/hrefs";
import { useDetail } from "../Detail";
import { AppLink } from "../ui";
import { DiagramCanvas } from "./DiagramCanvas";
import { usePartPanels } from "./PartDetail";
import { graphOf, type ViewKey } from "./useLayout";

/* The diagram, on any page: one view of the control system, or of the part of it a system, an item or a projection names,
   asking for its own graph. A click on a part opens its panel; opening a system or drilling into it happens here,
   not in the address; "Open on the Diagram page" goes to the whole page, drawn the same.
     <Diagram view="blocks" system="support" height={320} />
     <Diagram item="ticket/42" />          what an item passed through */

export interface DiagramProps {
  view?: ViewKey;
  system?: string;
  item?: string;
  projection?: string;
  around?: string;
  /** the Process view's projections, comma-separated */
  projections?: string;
  /** CSS height of the canvas (the page's diagram fills the window; an embedded one needs its own) */
  height?: number | string;
  every?: number | null;
  /** the caption over it; none: no caption */
  title?: string;
  className?: string;
}

export function Diagram({ view = "dynamics", system: system0 = "", item = "", projection = "", around = "", projections = "", height = 360, every = 5000, title, className }: DiagramProps) {
  const [system, setSystem] = useState(system0);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { setSystem(system0); setOpen(null); }, [system0]);   // asked for another system: drawn afresh
  const detail = useDetail();
  const params = {
    view, system, around,
    ...(view !== "process" ? { item, projection: item ? "" : projection, ...(open != null ? { open } : {}) } : { projections }),
  };
  const st = useApi<any>("graph", params, { every });
  const g = graphOf(view, st.data);

  const toggleSystem = useCallback((name: string) => {
    const now = new Set<string>(g?.open || []);
    if (now.has(name)) { now.delete(name); for (const [k, v] of Object.entries<any>(g?.tree || {})) if (v.within === name) now.delete(k); }
    else now.add(name);
    setOpen([...now].join(",") || "-");
  }, [g]);
  const drill = useCallback((name: string) => { setSystem(name); setOpen(""); }, []);
  const sysActs = useMemo(() => ({ toggleSystem, drill }), [toggleSystem, drill]);
  const pick = usePartPanels(g, view, sysActs);
  const captionId = useMemo(() => `diagram-${Math.random().toString(36).slice(2, 9)}`, []);

  return (
    <figure className={`diagram-embed${className ? ` ${className}` : ""}`} style={{ height }}>
      <DiagramCanvas g={g} view={view} scope={`${view}|${system}|${around}|${item}|${projection}`} labelledBy={title ? captionId : undefined}
        acts={{ pick, toggleSystem, drill, sel: detail.key }} fitTop={title ? 36 : 12} onBackground={detail.close}
        waiting={st.error ? `The server is not answering (${st.error.message}).` : "Loading…"}>
        <div className="toolbar">
          {title && <figcaption id={captionId} className="caption">{title}</figcaption>}
          {system !== system0 && <button type="button" onClick={() => drill(system0)}>Back to {system0 || "everything"}</button>}
          <AppLink to={diagramHref({ view, system, item, projection, around })} className="small">Open on the Diagram page</AppLink>
        </div>
      </DiagramCanvas>
    </figure>
  );
}
