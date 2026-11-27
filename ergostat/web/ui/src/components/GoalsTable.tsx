import { dur, FLAP_AT } from "../lib/format";
import { goalPerf, goalRank, steadyWord } from "../lib/goals";
import { useStatus } from "../state/status";
import { WINDOWS, useTime } from "../state/time";
import { GoalCells, type GoalColumn } from "./goals";
import { Table } from "./Table";

/* Goals as a table (/api/loops rows), those that need someone first: on the Goals page with every column, in a
   dashboard's goals panel with fewer. A row's click opens the goal (``onOpen``). */

export const ALL_COLUMNS: GoalColumn[] = ["goal", "status", "measure", "value", "bound", "far", "timeOff", "backIn", "spark", "performance", "acted", "card"];
export const PANEL_COLUMNS: GoalColumn[] = ["goal", "status", "measure", "value", "bound", "far", "spark", "card"];

const HEADS: Partial<Record<GoalColumn, [string, boolean?]>> = {
  goal: ["goal"], status: ["status"], measure: ["holds"], value: ["now", true], bound: ["r", true], far: ["how far", true],
  timeOff: ["time off", true], backIn: ["back in", true], spark: ["trend"], performance: ["behaviour"], acted: ["acted"],
};

export function GoalsTable({ loops, only, columns = ALL_COLUMNS, selected, onOpen, caption = "Goals", mark, label }: {
  loops: Record<string, any>;
  /** these goals alone (a panel's goals:, or a system's), else every one */
  only?: string[] | null;
  /** a row's class and title (an ancillary goal: greyer, saying where it is defined) */
  mark?: (name: string) => { className?: string; title?: string };
  label?: (name: string) => string;
  columns?: GoalColumn[];
  selected?: string | null;
  onOpen: (name: string) => void;
  caption?: string;
}) {
  const { status } = useStatus();
  const { since, at } = useTime();
  const full = WINDOWS[since] || status?.window || 0;
  const win = full ? Math.min(full, status?.first ? status.at - status.first : full) : 0;
  const project = status?.name || "";
  const word = (n: string, lp: any) => {
    const s = lp.perf;
    if (s == null || s.not_analysed) return "";
    if (lp.times_off >= FLAP_AT) return steadyWord(project, since, at, n, `flapping (${lp.times_off} crossings in ${dur(win)})`, win);
    if (s.working || s.failed) return goalPerf(s);
    return steadyWord(project, since, at, n, goalPerf(s), win);
  };
  const rows = Object.entries(loops).filter(([name]) => !only || only.includes(name))
    .map(([name, lp]) => ({ name, ...lp })).sort((a, b) => goalRank(a) - goalRank(b));
  return (
    <Table caption={caption} className="loops">
      <Table.Head>
        {columns.filter((c) => HEADS[c]).map((c) => <Table.Th key={c} num={HEADS[c]![1]}>{HEADS[c]![0]}</Table.Th>)}
      </Table.Head>
      <Table.Body>
        {rows.map((g) => (
          <Table.Row key={g.name} onClick={() => onOpen(g.name)} title={mark?.(g.name).title}
            className={[selected === g.name ? "selected" : "", mark?.(g.name).className || ""].join(" ").trim() || undefined}>
            <GoalCells g={{ ...g, behaviour: word(g.name, g), label: label?.(g.name) }} columns={columns} open={onOpen} at={at} />
          </Table.Row>
        ))}
      </Table.Body>
    </Table>
  );
}
