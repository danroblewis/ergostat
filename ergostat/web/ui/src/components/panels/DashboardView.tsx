import type { ReactNode } from "react";
import { PanelBox } from "./PanelBox";
import type { PanelDef } from "./types";

/* A dashboard's panels on the page's grid, each asking for its own answer: what any page made of panels draws. ``tools`` puts a page's own buttons in a panel's head (the editor's). */
export function DashboardView({ panels, every, refreshKey, tools }: {
  panels: PanelDef[]; every?: number | null; refreshKey?: unknown; tools?: (def: PanelDef, i: number) => ReactNode;
}) {
  return (
    <div className="panel-grid">
      {panels.map((def, i) => <PanelBox key={def.id || i} def={def} every={every} refreshKey={refreshKey} tools={tools?.(def, i)} />)}
    </div>
  );
}
