import { dur, fmt, nowS, op } from "./format";

/* A goal in words, the same wherever a goal is listed (the old goalrow.js): the server says its word and columns
   (state.goal_row); only these functions turn them into reader text. */

export const GOAL_WORDS = ["holding", "off", "stale", "open", "unknown"];
export const goalWord = (g: any): string => g?.word || (GOAL_WORDS.includes(g?.status) ? g.status : "unknown");
export const exceptional = (word: string) => !!word && word !== "holding";
export const goalRank = (g: any): number => ({ off: 0, open: 1, unknown: 2, holding: 3 } as Record<string, number>)[goalWord(g)] ?? 2;
export const goalBound = (g: any): string => op(g.row ? g.row.bound_words : `${g.setpoint ?? ""}${g.band || ""}`);
export const goalOffFor = (g: any, at: number | null): string | null =>
  goalWord(g) !== "off" ? null : g.off_since == null ? "off since ?"
    : `off ${g.off_before_window ? "over " : ""}${dur((at || nowS()) - g.off_since)}`;

const secs = (x: number | null | undefined) => (x == null ? "–" : x < 600 ? `${fmt(x)} s` : dur(x));
/** One word or two for how the loop is doing (control.js performanceWord). */
export function performanceWord(d: any): string {
  if (!d) return "";
  if (d.why) return "no one process";
  const pf = d.performance || {};
  if (pf.oscillation?.oscillating) return `oscillates, ${secs(pf.oscillation.period)}`;
  if (pf.saturation != null && pf.saturation > 0.2) return "saturated";
  if (pf.constraint) return pf.constraint.share ? "past its bound" : "within its bound";
  if (pf.harris?.index != null) return `Harris ${fmt(pf.harris.index)}`;
  if (pf.harris?.short) return "too little record";
  if (pf.harris?.needs_theta) return "needs θ";
  return "";
}
export const goalPerf = (s: any) =>
  s == null || s.not_analysed ? "" : s.working ? "being worked out" : s.failed ? "could not be worked out" : performanceWord(s);

/* a loop's behaviour, with hysteresis (pages.js steadyWord): its class (the words without their numbers) changes only
   once the new class has held for HOLD_SHARE of the window (a minute at least); kept in localStorage by project and
   window; a past moment shows its own word and keeps nothing */
const HOLD_SHARE = 0.05, PERF_EVERY = 300000;
export function steadyWord(project: string, since: string, at: number | null, name: string, word: string, win: number): string {
  if (at) return word;
  const key = `ergostat.behaviour.${project}.${since}.${name}`, now = Date.now(), hold = Math.max(60, HOLD_SHARE * win) * 1000;
  const cls = (w: string) => w.replace(/[\d(−-].*$/, "").replace(/[,\s]+$/, "");
  let k: any = null;
  try { k = JSON.parse(localStorage.getItem(key) || "null"); } catch { /* none kept */ }
  if (!k || typeof k.word !== "string" || !(now - k.seen < hold + 2 * PERF_EVERY)) k = { word, at: now };
  else if (cls(k.word) !== cls(word)) {
    if (k.next !== cls(word)) Object.assign(k, { next: cls(word), since: now });
    if (now - k.since >= hold) k = { word, at: now };
  } else {
    delete k.next;
    if (now - k.at >= hold) k = { word, at: now };
  }
  k.seen = now;
  try { localStorage.setItem(key, JSON.stringify(k)); } catch { /* this page only */ }
  return k.word;
}

export const setpointOf = (sp: string | null | undefined) => { const m = /(-?\d+(\.\d+)?)/.exec(sp || ""); return m ? +m[1] : null; };
