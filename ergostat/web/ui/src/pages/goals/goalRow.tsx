import { StatusWord } from "../../components";
import { dur, fmt, holdText, isLimit, nowS, op, shareText } from "../../lib/format";

/* One goal's row, drawn the same wherever a goal is listed (the old goalrow.js): the server says its word and columns
   (state.goal_row); only this file turns them into reader text. Used by Goals and the agent's page. */

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

/** A small line of a series against its setpoint (details.js sparkSvg). */
export function Spark({ points, w, h: hgt, setpoint = null }: { points: [number, number][]; w: number; h: number; setpoint?: number | null }) {
  const vs = points.map((p) => p[1]);
  let lo = Math.min(...vs), hi = Math.max(...vs);
  if (setpoint != null) { lo = Math.min(lo, setpoint); hi = Math.max(hi, setpoint); }
  const small = hgt < 50, pad = small ? 3 : 6, left = small ? 2 : 34;
  const y = (v: number) => hgt - pad - ((v - lo) / ((hi - lo) || 1)) * (hgt - 2 * pad);
  const d = vs.map((v, i) => `${i ? "L" : "M"}${left + (i / (vs.length - 1)) * (w - left - 4)},${y(v)}`).join("");
  return (
    <svg width={w} height={hgt} className="spark">
      {setpoint != null && <line x1={left} x2={w - 2} y1={y(setpoint)} y2={y(setpoint)} className="chart-set" />}
      <path d={d} className="chart-line" />
      {!small && <><text x={0} y={12} className="chart-tick">{fmt(hi)}</text><text x={0} y={hgt - 2} className="chart-tick">{fmt(lo)}</text></>}
    </svg>
  );
}

export type GoalColumn = "goal" | "status" | "measure" | "value" | "bound" | "far" | "timeOff" | "backIn" | "spark" | "performance" | "expected" | "acted" | "card";

/** The cells of one goal ({name, ...its /api/loops entry}), in the columns asked for. */
export function GoalCells({ g, columns, open, at }: { g: any; columns: GoalColumn[]; open: (name: string) => void; at: number | null }) {
  const cell = (c: GoalColumn) => {
    switch (c) {
      case "goal": return (
        <td key={c} className="nowrap">
          <button className="name" type="button" onClick={(ev) => { ev.stopPropagation(); open(g.name); }}><b>{g.name}</b></button>
          {g.open_loop && <span className="muted" title="Acts on its schedule, reads nothing"> open loop</span>}
        </td>);
      case "status": return <td key={c}><StatusWord status={goalWord(g)} /></td>;
      case "measure": return <td key={c} className="nowrap">{g.row?.measure ?? g.stock}</td>;
      case "value": return <td key={c} className="num">{fmt(g.row ? g.row.value : g.value)}</td>;
      case "bound": return <td key={c} className="num nowrap">{holdText(g.setpoint, g.band)}</td>;
      case "far": return <td key={c} className="num nowrap" data-off={g.name} title={`How far it is from its ${isLimit(g.setpoint) ? "limit" : "setpoint"}`}>{g.off_by_words || ""}</td>;
      case "timeOff": return <td key={c} className="num" title="The share of the window the goal spent off">{shareText(g.off_share)}</td>;
      case "backIn": return (
        <td key={c} className="num" title={g.back_in != null ? `Typically holding again this long after going off (slowest ${dur(g.back_in_slowest)}, ${g.times_off} times); its valve opens ${g.answers_in != null ? dur(g.answers_in) : "?"} after` : "It has not gone off and come back in the window"}>
          {g.back_in != null ? dur(g.back_in) : "–"}
        </td>);
      case "spark": return (
        <td key={c} className="spark-cell" title="Its scope: r and y, u, e over the window">
          {(g.points || []).length > 1 ? <Spark points={g.points} w={120} h={24} setpoint={setpointOf(g.setpoint)} /> : ""}
        </td>);
      case "performance": return (
        <td key={c} className="nowrap" data-perf={g.name} title="Flapping (gone off 20 times or more in the window), oscillating, saturated, past or within its bound, or its Harris index: from its scope, over the last day of record; on Goals it changes only once the new behaviour has held a while">
          {g.behaviour ?? goalPerf(g.perf)}
        </td>);
      case "expected": return <td key={c} className="muted">{g.row?.expected ?? ""}</td>;
      case "acted": return <td key={c} title="In the window, its sensor read and its controller decided or its valve opened">{g.observed ? "yes" : <span className="muted">no</span>}</td>;
      case "card": return (
        <td key={c} className="card">
          <div><b>{g.name}</b> · <StatusWord status={goalWord(g)} /></div>
          <div className="muted">
            {[`${fmt(g.value)} against ${op(g.setpoint)}`, goalOffFor(g, at), g.back_in != null ? `usually back in ${dur(g.back_in)}` : null].filter(Boolean).join(" · ")}
          </div>
        </td>);
    }
  };
  return <>{columns.map(cell)}</>;
}
