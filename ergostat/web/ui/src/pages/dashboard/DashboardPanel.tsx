import { lazy, Suspense, type ReactNode } from "react";
import { Loading, PanelFrame, QueryPanel } from "../../components";
import type { Panel } from "../../lib/query";

/* The diagram panel is loaded only when a dashboard has one: it brings ELK. */
const DiagramPanel = lazy(() => import("../../components/diagram/DiagramPanel"));

/** One panel, as its form says: a diagram, or a query's chart, stat or table. */
export function DashboardPanel({ panel, tools, every, refreshKey }: { panel: Panel; tools?: ReactNode; every?: number | null; refreshKey?: unknown }) {
  if (panel.form === "diagram")
    return (
      <Suspense fallback={<PanelFrame panel={panel} tools={tools} className="panel-form-diagram"><Loading /></PanelFrame>}>
        <DiagramPanel panel={panel} tools={tools} />
      </Suspense>
    );
  return <QueryPanel panel={panel} every={every} tools={tools} refreshKey={refreshKey} />;
}
