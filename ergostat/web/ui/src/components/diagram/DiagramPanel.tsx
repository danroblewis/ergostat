import type { ReactNode } from "react";
import { diagramOf } from "../../lib/hrefs";
import { PanelFrame } from "../charts/PanelView";
import type { PanelDef } from "../panels/types";
import { Diagram } from "./Diagram";

/* A diagram as a dashboard's panel ({panel: diagram, address: "/diagram?view=blocks&system=x"}): the panel's frame,
   title and tools, and in it the diagram its address names, asking for its own graph. */
export function DiagramPanel({ def, tools }: { def: PanelDef; tools?: ReactNode }) {
  const d = diagramOf(def.address || "/diagram");
  return (
    <PanelFrame panel={{ id: def.id || "", title: def.title || "", note: def.note, size: def.size, tall: def.tall, form: "diagram", queries: [] }}
      tools={tools} className="panel-form-diagram">
      <Diagram view={d.view} system={d.system} item={d.item} kind={d.kind} around={d.around} kinds={d.kinds} height="100%" className="in-panel" />
    </PanelFrame>
  );
}
export default DiagramPanel;
