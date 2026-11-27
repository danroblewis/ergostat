import { Muted, Page } from "../../components";
import { EditableDashboard, useEditing } from "../../components/panels/EditableDashboard";
import { pageDashboard } from "../../lib/pages";
import { useStatus } from "../../state/status";

/* A system's Overview (/overview for the top level, /SYSTEM/overview), a dashboard made in advance (lib/pages.ts): what
   needs attention there, its goals, its stocks and flows, and its projections, each panel scoped to the system
   ($system: what spec/scope.py says it contains; what is ancillary there drawn greyer). Edited in place, it is saved
   as the dashboard named overview of that system, in the system's file, and drawn here in place of this one. */

const BASE = pageDashboard("overview");
const EVERY = 5000;

export default function OverviewPage({ system }: { system: string }) {
  const { status } = useStatus();
  const ed = useEditing({ base: BASE, target: { name: "overview", system }, bind: { system } });
  return (
    <Page title={<>{system || status?.name || "Everything"}<Muted> · Overview</Muted></>} className="overview">
      <div className="page-edit">{ed.bar}</div>
      <EditableDashboard ed={ed} every={EVERY} />
    </Page>
  );
}
