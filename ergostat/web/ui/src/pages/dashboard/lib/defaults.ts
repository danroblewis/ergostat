/* The dashboard a project opens on, built from what the record holds (dashboard.js dashDefault): the lead kind's
   numbers in a row, its charts, then the next kinds'; with no kinds, the first series. Pure. The worked examples of
   each plot family (dashboard-examples.js) and the pipelines' SQL rows are not ported yet. */
import type { Dashboard, Panel, Query } from "./query";

const MONEY = /^(usd|eur|gbp|\$)/i, COST = /(^|[._-])(cost|spend|usd)([._-]|$)/i;
const REWORK = /fix|redo|rework|retry|replan/i;
const NOT_CHARTED = /(^|[._-])(id|ids|rank|seq|index|order|priority|number|at|ts|time|timestamp|epoch)$/i;
const WANTED = [
  { match: /attempt/i, word: "attempts", agg: "avg", rate: false },
  { match: /(^|[._-])net[._-]?lines?$/i, word: "net lines", agg: "sum", rate: true },
  { match: /loop.*(hour|minute|second)/i, word: "loop hours", agg: "avg", rate: false },
];
export const MOST = 32;
const RECENT = 10;

interface Field { name: string; unit?: string }
interface Kind {
  name: string; states: string[]; open: string[]; done: string[]; stopped: string[]; waiting: string[]; working: string[];
  midway: number; score: number; held: number; inWork: number; now: Record<string, number>; fields: Field[];
}
const isCost = (f: Field) => COST.test(f.name) || MONEY.test(f.unit || "");
const costUnit = (f: Field) => (MONEY.test(f.unit || "") ? f.unit! : "usd");

function kindOf(name: string, k: any, info: any, queue?: string[]): Kind {
  const states: string[] = k.states || [], now: Record<string, number> = info?.counts || {};
  const done = ((info?.finished || states.slice(-1)) as string[]).filter((x) => states.includes(x));
  const stopped = states.filter((x) => (info?.paused || []).includes(x) || (x === "dead" && info?.dead !== false && !done.includes(x)));
  const open = states.filter((x) => !done.includes(x) && !stopped.includes(x));
  const waits = new Set(queue || states.slice(0, 1));
  const waiting = open.filter((x) => waits.has(x)), working = open.filter((x) => !waits.has(x));
  const sum = (list: string[]) => list.reduce((n, x) => n + (now[x] || 0), 0);
  const self = Object.values(info?.relations || {}).some((to) => Array.isArray(to) && to.includes(name));
  const midway = states.slice(1).filter((x) => open.includes(x)).length;
  const score = (info?.finished_from === "declared" ? 4 : 0) + (self ? 3 : 0) + (stopped.length ? 1 : 0) +
    Math.min(midway, 6) + (sum(open) ? 1 : 0) - (midway < 2 ? 6 : 0);
  return { name, states, open, done, stopped, waiting, working, midway, score, held: sum(states), inWork: sum(open), now, fields: k.fields || [] };
}

function kindsOf(fields: any, infos: any[] = [], queues: Record<string, string[]> = {}): Kind[] {
  const by = new Map(infos.map((x) => [x.name, x]));
  const kinds = Object.entries(fields?.sources?.items?.kinds || {}).map(([name, k]) => kindOf(name, k, by.get(name), queues[name]))
    .filter((k) => k.states.length);
  const own = (k: Kind) => (k.name.startsWith("ergostat.") ? 1 : 0);
  kinds.sort((a, b) => own(a) - own(b) || b.score - a.score || b.inWork - a.inWork || b.held - a.held || a.name.localeCompare(b.name));
  return kinds.some((k) => k.held) ? kinds.filter((k) => k.held) : kinds;
}

/** The states work waits in, for the three leading kinds and the kinds their relations name. */
export function queuesOf(fields: any, infos: any[]): Record<string, string[]> {
  const by = new Map(infos.map((x) => [x.name, x])), moves = fields?.sources?.moves?.kinds || {}, queues: Record<string, string[]> = {};
  const todo = kindsOf(fields, infos).filter((k) => !k.name.startsWith("ergostat.")).slice(0, 3).map((k) => k.name);
  for (const seen = new Set(todo); todo.length;) {
    const name = todo.shift()!;
    if (moves[name]?.queue?.length) queues[name] = moves[name].queue;
    for (const to of Object.values(by.get(name)?.relations || {}).flat())
      if (typeof to === "string" && !seen.has(to)) { seen.add(to); todo.push(to); }
  }
  return queues;
}

function stayStates(k: Kind): string[] {
  const most = (list: string[], n: number) => list.filter((x) => !REWORK.test(x)).sort((a, b) => (k.now[b] || 0) - (k.now[a] || 0)).slice(0, n);
  const picked = new Set([...most(k.waiting, 2), ...most(k.working, 1)]);
  return k.states.filter((x) => picked.has(x));
}
const rate = { agg: "count", transform: "rate", rate_per: "hour" };
const arrivals = (k: Kind): Query => ({ id: "a", source: "moves", kind: k.name, measure: "entries", first_only: true, state: k.states.slice(0, 1), ...rate, label: "arrivals" });
const completions = (k: Kind): Query => ({ id: "b", source: "moves", kind: k.name, measure: "entries", state: k.done, ...rate, label: "completions" });
const count = (k: Kind, id: string, state: string[], label: string): Query => ({ id, source: "counts", kind: k.name, state, group_by: "kind", agg: "last", transform: "none", label });
const stay = (k: Kind, id: string, state: string, agg = "p50"): Query => ({ id, source: "moves", kind: k.name, measure: "time_in_state", state: [state], agg, transform: "none", label: state });
const costQuery = (k: Kind, f: Field): Query => ({ id: "a", source: "items", kind: k.name, field: f.name, agg: "sum", transform: "rate", rate_per: "hour", label: "cost" });
const legend = (values = ["last", "max"]) => ({ legend: "right", legend_values: values });
type Draft = Omit<Panel, "id">;
const stat = (title: string, query: Query, unit: string, decimals?: number): Draft => ({
  title, form: "stat", size: "s", queries: [query],
  ...(query.transform === "rate" ? { note: "recent average", display: { unit, decimals, recent: RECENT } } : { display: { unit, decimals } }),
});
const stayStat = (k: Kind, state: string): Draft => ({
  ...stat(`${k.name}: median wait of items that left ${state}`, stay(k, "a", state), "s"),
  note: "whole window", display: { unit: "s", whole: true, still: { kind: k.name, state } },
});

function kindPanels(k: Kind): Draft[] {
  const out: Draft[] = [];
  if (k.done.length) out.push({ title: `${k.name}: arrivals and completions per hour`, form: "line", queries: [arrivals(k), completions(k)],
    display: { unit: "/h", decimals: 1, ...legend(), y: { min: 0 } } });
  const groups = ([["waiting", k.waiting], ["working", k.working], ["stopped", k.stopped]] as [string, string[]][]).filter(([, s]) => s.length);
  if (groups.length) out.push({ title: `${k.name}: work by state`, form: "stacked",
    queries: groups.map(([word, s], i) => count(k, "abc"[i], s, word)), display: { unit: "items", decimals: 0, ...legend(["last"]), y: { min: 0 } } });
  const stays = stayStates(k);
  if (stays.length) out.push({ title: `${k.name}: median time in ${stays.join(", ")}`, form: "line",
    queries: stays.map((x, i) => stay(k, "abc"[i], x)), display: { unit: "s", ...legend(), y: { min: 0 } } });
  return out;
}
function fieldPanel(k: Kind, f: Field, want?: (typeof WANTED)[number]): Draft {
  const unit = f.unit && f.unit !== "count" ? f.unit : "";
  const word = want?.word || f.name;
  return { title: `${k.name}: ${word}${want?.rate ? " per hour" : want?.agg === "avg" ? ", average" : ""}`, form: "line", size: "m",
    queries: [{ id: "a", source: "items", kind: k.name, field: f.name, agg: want?.agg || "avg", ...(want?.rate ? { transform: "rate", rate_per: "hour" } : { transform: "none" }), label: word }],
    display: { unit: want?.rate ? `${unit || "items"}/h` : unit, ...legend() } };
}

export function defaultDashboard(fields: any, infos: any[] = [], queues: Record<string, string[]> = {}): Dashboard {
  const kinds = kindsOf(fields, infos, queues), panels: Draft[] = [], lead = kinds[0];
  if (lead) {
    const costKind = lead.fields.some(isCost) ? lead : kinds.find((k) => k.fields.some(isCost));
    const cost = costKind && (costKind.fields.find((f) => MONEY.test(f.unit || "")) || costKind.fields.find(isCost));
    const cu = cost ? `${costUnit(cost)}/h` : "";
    const stays = stayStates(lead);
    if (lead.open.length) panels.push(stat(`${lead.name}: work in progress`, count(lead, "a", lead.open, "in progress"), "items", 0));
    if (lead.done.length) panels.push(stat(`${lead.name}: completions per hour`, completions(lead), "/h", 1));
    if (stays[0]) panels.push(stayStat(lead, stays[0]));
    if (cost && costKind) {
      panels.push(stat(`${lead.name}: arrivals per hour`, arrivals(lead), "/h", 1));
      if (stays[1]) panels.push(stayStat(lead, stays[1]));
      panels.push(stat(`${costKind.name}: cost per hour`, costQuery(costKind, cost), cu, 2));
    }
    const first: Draft[] = kindPanels(lead).map((p) => ({ ...p, size: "m" as const }));
    if (cost && costKind) first.push({ title: `${costKind.name}: cost per hour`, form: "area", size: "m", queries: [costQuery(costKind, cost)],
      display: { unit: cu, decimals: 2, ...legend(), y: { min: 0 } } });
    const asked = WANTED.map((want) => ({ want, f: lead.fields.find((f) => want.match.test(f.name)) })).filter((x) => x.f);
    const worth = asked.length ? asked : lead.fields.filter((f) => !isCost(f) && !NOT_CHARTED.test(f.name) && f.unit && f.unit !== "count")
      .slice(0, 2).map((f) => ({ f, want: undefined }));
    for (const { want, f } of worth) first.push(fieldPanel(lead, f!, want));
    if (first.length % 2) first[first.length - 1].size = "full";
    panels.push(...first);
    for (const k of kinds.slice(1).filter((x) => x.inWork && x.midway >= 2 && !x.name.startsWith("ergostat.")).slice(0, 2)) {
      const row = kindPanels(k);
      const size = ({ 1: "full", 2: "m", 3: "s" } as const)[row.length as 1 | 2 | 3];
      panels.push(...row.map((p) => ({ ...p, size })));
    }
  } else {
    for (const x of (fields?.sources?.series?.series || []).slice(0, 6))
      panels.push({ title: x.name, form: "line", size: "m", queries: [{ id: "a", source: "series", series: x.name, agg: "last", transform: "none" }],
        display: { unit: x.unit || "", ...legend() } });
  }
  return { title: "Overview", since: null, panels: panels.slice(0, MOST).map((p, i) => ({ note: "", tall: false, ...p, id: `p${i + 1}` })) };
}

/** A rate's number read as the average of the last ``n`` buckets, so it does not say 0/h between bursts. */
export function recent(values: (number | null)[], n: number): (number | null)[] {
  return values.map((_, i) => {
    let sum = 0, weight = 0;
    for (let k = Math.max(0, i - n + 1); k <= i; k++) if (values[k] != null) { sum += values[k]!; weight++; }
    return weight ? sum / weight : null;
  });
}
