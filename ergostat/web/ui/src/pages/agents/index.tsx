import { Page } from "../../components";
import { EditableDashboard, useEditing } from "../../components/panels/EditableDashboard";
import { useApi } from "../../hooks/useApi";
import { pageDashboard } from "../../lib/pages";

/* Agents (pages.js pageAgents): a built-in dashboard of the agents group's panels: the ladder, one list by rung from
   the most general agent to none with what each costs in the window, and the daemons (when there are any). Each
   system has one (/agents, /SYSTEM/agents): the agents it contains. Edited in place, it is saved as the dashboard
   named agents of that system, drawn here in place of this page. */

const BASE = pageDashboard("agents");

const EVERY = 3000;

export default function AgentsPage({ system = "" }: { system?: string }) {
  const daemons = useApi<Record<string, any>>("daemons", {}, { every: EVERY });
  const some = Object.keys(daemons.data || {}).length > 0;
  const ed = useEditing({ base: BASE, target: { name: "agents", system }, bind: { system } });
  return (
    <Page title="Agents">
      <div className="page-edit">{ed.bar}</div>
      <EditableDashboard ed={ed} every={EVERY} only={(d) => d.panel !== "daemons" || some} />
    </Page>
  );
}
