import { Page } from "../../components";
import { DashboardView } from "../../components/panels/DashboardView";
import { useApi } from "../../hooks/useApi";
import { AGENTS_PANELS } from "../../lib/pages";

/* Agents (pages.js pageAgents): a built-in dashboard of the agents group's panels: the ladder, one list by rung from
   the most general agent to none with what each costs in the window, and the daemons (when there are any). */

const EVERY = 3000;

export default function AgentsPage() {
  const daemons = useApi<Record<string, any>>("daemons", {}, { every: EVERY });
  const some = Object.keys(daemons.data || {}).length > 0;
  return (
    <Page title="Agents">
      <DashboardView panels={AGENTS_PANELS.filter((d) => d.panel !== "daemons" || some)} every={EVERY} />
    </Page>
  );
}
