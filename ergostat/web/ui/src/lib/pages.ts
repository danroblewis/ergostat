import type { DashboardDef, PanelDef } from "../components/panels/types";

/* ergostat's own pages as the dashboards they are: each one's panels, as a dashboard under `dashboards:` would
   declare them (SPEC §4f). A page draws these (with its own head and filters around them), and is edited where it is
   drawn (components/panels/EditableDashboard.tsx): saved, it is the model's own dashboard in its place (each system's
   `overview`, `goals`, `agents`, `events` by name, in that system's file; `page: agent`; a projection's own
   `dashboards: list:` and `show:`), drawn at its address instead (lib/systemRoutes.ts). Every one is a system's: its
   panels write `$system`, the system whose address it is drawn at ("" the top level). A page that shows one thing
   writes it `$agent`, `$item` or `$projection`: taken from the address. */

export const full = (d: PanelDef): PanelDef => ({ size: "full", fit: true, ...d });

/** A system's Overview: what needs attention there, its goals, its stocks and flows, its projections. */
export const OVERVIEW_PANELS: PanelDef[] = [
  { panel: "attention", id: "attention", title: "What needs attention", system: "$system" },
  { panel: "goals", id: "goals", title: "Its goals", system: "$system" },
  { panel: "chart", id: "parts", title: "Its stocks and flows", system: "$system", fit: false },
  { panel: "projections", id: "projections", title: "Its projections", system: "$system" },
].map(full);

/** A system's Goals: at the top, the goals off (each saying where its loop is stuck), the model's housekeeping and the
 *  suggestions (one attention panel, its own headings: housekeeping and suggestions folded); then the quiet systems
 *  and every goal. */
export const GOALS_PANELS: PanelDef[] = [
  { panel: "attention", id: "attention", show: ["off", "housekeeping", "suggestions"], system: "$system" },
  { panel: "quiet-systems", id: "quiet", title: "Quiet systems", quiet: true },
  { panel: "goals", id: "goals", title: "Every goal", columns: "all", system: "$system" },
].map(full);

export const AGENTS_PANELS: PanelDef[] = [
  { panel: "ladder", id: "ladder", title: "The ladder", system: "$system" },
  { panel: "agents", id: "agents", title: "Agents, by rung", system: "$system" },
  { panel: "daemons", id: "daemons", title: "Daemons" },
].map(full);

/** A system's Inbox: the built-in projection ergostat.inbox's list page (what it is, its graph of states, its items):
 *  each decision waiting on a person (what `ergostat inbox` lists) a card answered in place, then everything it asked
 *  before, answered or not. */
export const INBOX_PANELS: PanelDef[] = [
  { panel: "projection-summary", id: "summary", projection: "ergostat.inbox" },
  { panel: "projection-states", id: "states", projection: "ergostat.inbox" },
  { panel: "item-list", id: "items", title: "Waiting for you, then everything asked", projection: "ergostat.inbox", finished: "show" },
].map(full);

/** A system's Events: those behind what it contains (its projections' items, its blocks' and agents' own). */
export const EVENTS_PANELS: PanelDef[] = [{ panel: "events", id: "events", title: "Events, newest first", system: "$system" }].map(full);

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
  { panel: "item-state-timeline", id: "state-timeline", quiet: true },
  { panel: "item-field-chart", id: "numbers", quiet: true },
  { panel: "item-events-histogram", id: "events-over-time", quiet: true },
  { panel: "item-path", id: "path", quiet: true },
  { panel: "item-relations", id: "relations", quiet: true },
  { panel: "item-fields", id: "fields" },
  { panel: "item-refused", id: "refused", quiet: true },
  { panel: "item-moves", id: "moves" },
  { panel: "item-events", id: "events" },
  { panel: "item-changes", id: "changes" },
].map((d) => full({ ...d, item: "$item" }));

/** A projection's page: what it is (its name, count, description, system), its graph of states, its state now, its
 *  place in the model, then its items. */
export const PROJECTION_PANELS: PanelDef[] = [
  full({ panel: "projection-summary", id: "summary", projection: "$projection" }),
  full({ panel: "projection-states", id: "states", projection: "$projection" }),
  { panel: "projection-now", id: "now", title: "Now", size: "m", fit: true, projection: "$projection" },
  { panel: "projection-model", id: "model", title: "In the model", size: "m", fit: true, projection: "$projection" },
  full({ panel: "item-list", id: "items", title: "Items", projection: "$projection" }),
];

export type PageName = "overview" | "goals" | "agents" | "events" | "inbox" | "agent" | "item" | "projection";

/** ergostat's own pages made of panels, and the address's word one of one thing takes (`page:` names those). */
export const PAGES: Record<PageName, { title: string; panels: PanelDef[]; binds?: "agent" | "item" | "projection" }> = {
  overview: { title: "Overview", panels: OVERVIEW_PANELS },
  goals: { title: "Goals", panels: GOALS_PANELS },
  agents: { title: "Agents", panels: AGENTS_PANELS },
  events: { title: "Events", panels: EVENTS_PANELS },
  inbox: { title: "Inbox", panels: INBOX_PANELS },
  agent: { title: "An agent", panels: AGENT_PANELS, binds: "agent" },
  item: { title: "An item", panels: ITEM_PANELS, binds: "item" },
  projection: { title: "A projection", panels: PROJECTION_PANELS, binds: "projection" },
};

/** A page as a dashboard: its title and panels, `$WORD`s filled in from `bind` when given. */
export function pageDashboard(page: PageName, bind: Record<string, string> = {}): DashboardDef {
  const p = PAGES[page];
  const fill = (v: unknown) => (typeof v === "string" && v.startsWith("$") && bind[v.slice(1)] != null ? bind[v.slice(1)] : v);
  return { title: p.title, panels: p.panels.map((d) => Object.fromEntries(Object.entries(d).map(([k, v]) => [k, fill(v)])) as PanelDef) };
}

/** The default dashboards every system has, in the nav bar's order, with their links' words (spec/routes.py
 *  DEFAULTS). */
export const DEFAULTS: [string, string][] = [
  ["overview", "Overview"], ["diagrams", "Diagrams"], ["goals", "Goals"], ["agents", "Agents"], ["events", "Events"],
  ["inbox", "Inbox"],
];
