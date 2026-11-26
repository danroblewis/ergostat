import type { ReactNode } from "react";
import type { Panel } from "../../lib/query";
import { PanelFrame } from "../charts/PanelView";
import { Diagram } from "./Diagram";

/* A diagram as a dashboard's panel (form "diagram"): the panel's frame, title and tools, and in it the diagram its
   ``diagram`` names, asking for its own graph. */
export function DiagramPanel({ panel, tools }: { panel: Panel; tools?: ReactNode }) {
  const d = panel.diagram || {};
  return (
    <PanelFrame panel={panel} tools={tools} className="panel-form-diagram">
      <Diagram view={d.view || "dynamics"} system={d.system} item={d.item} kind={d.kind} height="100%" className="in-panel" />
    </PanelFrame>
  );
}
export default DiagramPanel;
