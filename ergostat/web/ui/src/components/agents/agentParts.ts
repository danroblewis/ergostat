import { ago, dur } from "../../lib/format";

/* An agent's words, shared by the Agents list and an agent's own page (details.js, pages.js). */

/** Its roles, each valve with the goal it serves: "valve work → goal located-worked". */
export const rolesText = (roles: any[] | undefined): string =>
  (roles || []).map((r) => `${r.kind} ${r.name}` + (r.goal ? ` → goal ${r.goal}` : "")).join(", ");

/** How it is set going: its schedule, per item by its lease, on demand, or not by ergostat. */
export const engagedText = (a: any): string => a.collects ? `continuously: its daemon ${a.collects.name} prints its events`
  : a.schedule || (a.leased ? "started per item by its lease, not on a schedule"
  : a.runs_itself ? "on demand, not on a schedule" : "not run by ergostat");

const sched = (a: any) => a.schedule || (a.every ? `every ${dur(a.every)}` : "");
/** An agent that stands out: it last failed, never ran on its schedule, or ran under half the runs asked. [word, why] */
export function exception(a: any): [string, string] | null {
  if (a.collects) {                                 // a collector: no runs; its daemon is what it does
    const d = a.collects;
    if (!d.state || d.state === "running" || String(d.state).startsWith("running")) return null;
    return [`daemon ${d.state}`, `its daemon ${d.name} is ${d.state}` + (d.why ? `: ${d.why}` : "") + ", so its events stop"];
  }
  if (a.failing) return ["last run failed", `its last run, ${ago(a.last?.time)}, failed${a.last?.data?.note ? ": " + a.last.data.note : ""}`];
  if (!a.last && (a.runs_itself || a.every || a.cron)) {
    return ["never ran", `${sched(a) || "it runs itself"}, but no run of it is in the record` + (a.runs_itself ? "" : " (it is not run here: whatever runs it records nothing)")];
  }
  if (a.expected >= 4 && a.runs < a.expected / 2) {
    return [`behind: ${a.runs} of ~${a.expected}`, `${sched(a)} over the ${dur(a.span)} of record in the window asks for about ${a.expected} runs; ${a.runs} are recorded`];
  }
  return null;
}

/** When it last ran, or why that is not asked. */
export const lastText = (a: any): string => a.collects
  ? (a.collects.last_line ? `last event line ${ago(a.collects.last_line)}` : `daemon ${a.collects.state || "not started"}, no line yet`)
  : a.runs_itself
  ? (a.running_since ? `running for ${ago(a.running_since).replace(" ago", "")}` : a.last ? ago(a.last.time) : "never ran")
  : a.kind === "person" ? "a person" : "not run here";

/** What it did in the window, as rows: its runs' tally, durations, stale readings, its daemon. */
export function agentTally(a: any): [string, string | null][] {
  const ss = (a.recent || []).slice(-40).map((e: any) => e.data.seconds).filter((x: any) => x != null);
  const d = a.daemon;
  return [
    ["in window", `${a.runs} runs: ${a.runs - a.failed - (a.pool_full || 0)} done, ` + (a.pool_full ? `${a.pool_full} refused (workspace pool full), ` : "")
      + `${a.failed} failed` + (a.refused ? `, ${a.refused} lines refused` : "") + (a.unread ? `, ${a.unread} unreadable` : "")],
    ["durations", ss.length ? `${Math.min(...ss)}s to ${Math.max(...ss)}s over its last ${ss.length} runs` : null],
    ["stale", (a.stale || []).length ? `no recent reading from ${a.stale.join(", ")}` : null],
    ["daemon", d ? `${d.name}: ${d.state || "not started"}` + (d.pid ? `, pid ${d.pid}` : "") + `, ${d.restarts || 0} restarts`
      + (d.last_line ? `, last line ${ago(d.last_line)}` : "") + (d.alarm ? ` (alarm: ${d.alarm.why})` : "")
      + (d.processes ? "; " + Object.entries(d.processes).map(([k, v]: [string, any]) => `#${k.split("#").pop()} ${v.state}` + (v.pid ? ` (pid ${v.pid})` : "")).join(", ") : "") : null],
  ];
}
