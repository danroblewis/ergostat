import { Page } from "../../components";
import { DashboardView } from "../../components/panels/DashboardView";
import type { PanelDef } from "../../components/panels/types";
import { useApi } from "../../hooks/useApi";

/* Agents (pages.js pageAgents): a built-in dashboard of the agents group's panels: the ladder, one list by rung from
   the most general agent to none with what each costs in the window, and the daemons (when there are any). */

const EVERY = 3000;
export const AGENTS_PANELS: PanelDef[] = [
  { panel: "ladder", id: "ladder", title: "The ladder", size: "full", fit: true },
  { panel: "agents", id: "agents", title: "Agents, by rung", size: "full", fit: true },
  { panel: "daemons", id: "daemons", title: "Daemons", size: "full", fit: true },
];

export default function AgentsPage() {
  const daemons = useApi<Record<string, any>>("daemons", {}, { every: EVERY });
  const some = Object.keys(daemons.data || {}).length > 0;
  return (
    <Page title="Agents">
      <DashboardView panels={AGENTS_PANELS.filter((d) => d.panel !== "daemons" || some)} every={EVERY} />
    </Page>
  );
}
