import { dur, fmt, holdText, isLimit, op, shareText } from "../lib/format";
import { goalOffFor, goalPerf, goalWord, setpointOf } from "../lib/goals";
import { Spark } from "./charts/Spark";
import { StatusWord } from "./ui";

/* One goal's row, drawn the same wherever a goal is listed: the cells of the columns asked for, so a table of goals
   on any page is <tr>{<GoalCells g={g} columns={[...]} />}</tr>. Its words are lib/goals.ts's. */

export type GoalColumn = "goal" | "status" | "measure" | "value" | "bound" | "far" | "timeOff" | "backIn" | "spark" | "performance" | "expected" | "acted" | "card";

/** The cells of one goal ({name, ...its /api/loops entry}), in the columns asked for. */
export function GoalCells({ g, columns, open, at }: { g: any; columns: GoalColumn[]; open: (name: string) => void; at: number | null }) {
  const cell = (c: GoalColumn) => {
    switch (c) {
      case "goal": return (
        <td key={c} className="nowrap">
          <button className="name" type="button" onClick={(ev) => { ev.stopPropagation(); open(g.name); }}><b>{g.label ?? g.name}</b></button>
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
