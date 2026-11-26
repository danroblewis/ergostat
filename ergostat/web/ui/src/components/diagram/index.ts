/* The diagram, on any page (imported from "components/diagram", not from "components": it brings ELK, so only the
   pages that draw one load it):
     <Diagram view="blocks" system="x" height={320} />    asks for its graph itself
     <DiagramCanvas g={graph} view="dynamics" acts={...} scope="..." />    draws a graph a page already has
   and the parts they are made of: the three drawings, the layout (useDiagramLayout), pan and zoom, a part's panel. */
export { Diagram, type DiagramProps } from "./Diagram";
export { DiagramPanel } from "./DiagramPanel";
export { DiagramCanvas, exportSvg, type DiagramCanvasProps } from "./DiagramCanvas";
export { DynamicsDrawing, type Acts } from "./Dynamics";
export { BlocksDrawing } from "./Blocks";
export { ProcessDrawing, pmLabel } from "./Process";
export { BlockPanel, ProcessPanel, SdPartPanel, SystemPanel, usePartPanels } from "./PartDetail";
export { usePanZoom, type View } from "./usePanZoom";
export { boundsOf, emptyText, graphOf, useDiagramLayout, type ViewKey } from "./useLayout";
export type { Layout } from "./layout";
