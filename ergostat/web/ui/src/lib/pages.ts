import type { DashboardDef, PanelDef } from "../components/panels/types";

/* ergostat's own pages as the dashboards they are: each one's panels, as a dashboard under `dashboards:` would
   declare them (SPEC §4f). A page draws these (with its own head and filters around them); the Dashboard page offers
   each as a copy to start a draft from; a dashboard the model declares under a page's name is drawn at its address
   instead (lib/routes.ts), and one declared with `page: agent|item|kind` is drawn for every agent, item or kind. A
   page that shows one thing writes it `$agent`, `$item` or `$kind`: taken from the address. */

export const full = (d: PanelDef): PanelDef => ({ size: "full", fit: true, ...d });

export const GOALS_PANELS: PanelDef[] = [
  { panel: "quiet-systems", id: "quiet", title: "Quiet systems", quiet: true },
  { panel: "goals", id: "goals", title: "Every goal", columns: "all" },
].map(full);

export const AGENTS_PANELS: PanelDef[] = [
  { panel: "ladder", id: "ladder", title: "The ladder" },
  { panel: "agents", id: "agents", title: "Agents, by rung" },
  { panel: "daemons", id: "daemons", title: "Daemons" },
].map(full);


export const RECORD_PANELS: PanelDef[] = [{ panel: "events", id: "record", title: "Events, newest first" }].map(full);

/** An agent's page, by the anchor each panel is drawn under. */
export const AGENT_PANELS: PanelDef[] = [
  { panel: "agent-what", id: "what-it-is" },
  { panel: "agent-definition", id: "its-definition" },
  { panel: "agent-place", id: "its-place" },
  { panel: "agent-runs", id: "what-it-did" },
  { panel: "agent-log", id: "its-log" },
].map((d) => full({ ...d, agent: "$agent" }));

/** An item's page: a part with nothing to say (quiet) is not drawn. */
export const ITEM_PANELS: PanelDef[] = [
  { panel: "item-why", id: "why", quiet: true },
  { panel: "item-summary", id: "summary" },
  { panel: "item-path", id: "path", quiet: true },
  { panel: "item-relations", id: "relations", quiet: true },
  { panel: "item-fields", id: "fields" },
  { panel: "item-refused", id: "refused", quiet: true },
  { panel: "item-moves", id: "moves" },
  { panel: "item-events", id: "events" },
  { panel: "item-changes", id: "changes" },
].map((d) => full({ ...d, item: "$item" }));

/** A kind's page: its state now, its place in the model, its definition, then its items. */
export const KIND_PANELS: PanelDef[] = [
  { panel: "kind-now", id: "now", title: "Now", size: "m", fit: true, kind: "$kind" },
  { panel: "kind-model", id: "model", title: "In the model", size: "m", fit: true, kind: "$kind" },
  full({ panel: "kind-definition", id: "definition", title: "Definition", folded: true, kind: "$kind" }),
  full({ panel: "item-list", id: "items", title: "Items", kind: "$kind" }),
];

export type PageName = "goals" | "agents" | "record" | "agent" | "item" | "kind";

/** ergostat's own pages made of panels, and the address's word one of one thing takes (`page:` names those). */
export const PAGES: Record<PageName, { title: string; panels: PanelDef[]; binds?: "agent" | "item" | "kind" }> = {
  goals: { title: "Goals", panels: GOALS_PANELS },
  agents: { title: "Agents", panels: AGENTS_PANELS },
  record: { title: "Record", panels: RECORD_PANELS },
  agent: { title: "An agent", panels: AGENT_PANELS, binds: "agent" },
  item: { title: "An item", panels: ITEM_PANELS, binds: "item" },
  kind: { title: "A kind of item", panels: KIND_PANELS, binds: "kind" },
};

/** A page as a dashboard: its title and panels, `$WORD`s filled in from `bind` when given. */
export function pageDashboard(page: PageName, bind: Record<string, string> = {}): DashboardDef {
  const p = PAGES[page];
  const fill = (v: unknown) => (typeof v === "string" && v.startsWith("$") && bind[v.slice(1)] != null ? bind[v.slice(1)] : v);
  return { title: p.title, panels: p.panels.map((d) => Object.fromEntries(Object.entries(d).map(([k, v]) => [k, fill(v)])) as PanelDef) };
}
