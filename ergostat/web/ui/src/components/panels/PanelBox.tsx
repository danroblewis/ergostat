import type { ReactNode } from "react";
import { PanelFrame } from "../charts/PanelView";
import { asQueryPanel, KINDS } from "./kinds/index";
import type { PanelDef } from "./types";

/* One panel of any kind, framed: what a dashboard, or any page, draws for a declaration. A kind it does not know is
   said, never dropped. */
export function PanelBox({ def, every, refreshKey, tools }: { def: PanelDef; every?: number | null; refreshKey?: unknown; tools?: ReactNode }) {
  const kind = KINDS[def.panel];
  if (kind?.Frame) return <kind.Frame def={def} every={every} refreshKey={refreshKey} tools={tools} />;
  return (
    <PanelFrame panel={asQueryPanel(def)} tools={tools} className={`panel-kind-${def.panel}`}>
      {kind?.Body ? <kind.Body def={def} every={every} refreshKey={refreshKey} />
        : <p className="note lvl-error">Not a kind of panel: {String(def.panel)} (known: {Object.keys(KINDS).join(", ")}).</p>}
    </PanelFrame>
  );
}
