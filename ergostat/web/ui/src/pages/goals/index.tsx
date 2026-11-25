import { useCallback, useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { Async, Muted, Note, Page, Table, useDetail } from "../../components";
import { useApi } from "../../hooks/useApi";
import { dur, FLAP_AT } from "../../lib/format";
import { goalsOff, useStatus } from "../../state/status";
import { WINDOWS, useTime } from "../../state/time";
import { GoalCells, goalPerf, goalRank, steadyWord, type GoalColumn } from "./goalRow";
import { GoalDetail } from "./GoalDetail";
import { windowNote } from "./parts";

/* Goals (the old pages.js pageLoops): every goal, those that need someone first; a click opens its detail beside the
   page, the goal chosen kept in the address (?select=NAME). */

const COLUMNS: GoalColumn[] = ["goal", "status", "measure", "value", "bound", "far", "timeOff", "backIn", "spark", "performance", "acted", "card"];

export default function GoalsPage() {
  const loops = useApi<Record<string, any>>("loops", { perf: 1 }, { every: 3000 });
  const systems = useApi<any[]>("systems", {}, { every: 3000 });
  const { status } = useStatus();
  const { since, at } = useTime();
  const detail = useDetail();
  const [q, setQ] = useSearchParams();
  const selected = q.get("select");

  const open = useCallback((name: string) => {
    setQ((p) => { const n = new URLSearchParams(p); n.set("select", name); return n; }, { replace: true });
  }, [setQ]);
  const shown = useRef<string | null>(null);
  useEffect(() => {
    if (selected && detail.key !== `goal:${selected}`) detail.open(`goal:${selected}`, <GoalDetail key={selected} name={selected} />);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);
  // the panel closed (or showing something else): the address forgets the goal
  useEffect(() => {
    const was = shown.current;
    shown.current = detail.key;
    if (was?.startsWith("goal:") && detail.key !== was && selected === was.slice(5)) {
      setQ((p) => { const n = new URLSearchParams(p); n.delete("select"); return n; }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.key]);

  const off = goalsOff(status);
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
  const w = windowNote(status);

  return (
    <Page title={<>Goals{status && <Muted>{` · goals off ${off.off}${off.upkeep ? ` · model upkeep ${off.upkeep}` : ""}`}</Muted>}</>}>
      <div className="quiet-systems">
        {(systems.data || []).filter((s) => s.quiet).map((s) => (
          <p key={s.name} className="quiet-line" data-system={s.name}><b>{s.name}</b>: {s.quiet}</p>
        ))}
      </div>
      <Async state={loops}>
        {(data) => {
          const rows = Object.entries(data).map(([name, lp]) => ({ name, ...lp })).sort((a, b) => goalRank(a) - goalRank(b));
          return (
            <Table caption="Goals" className="loops">
              <Table.Head>
                <Table.Th>goal</Table.Th><Table.Th>status</Table.Th><Table.Th>holds</Table.Th><Table.Th num>now</Table.Th>
                <Table.Th num>r</Table.Th><Table.Th num>how far</Table.Th><Table.Th num>time off</Table.Th><Table.Th num>back in</Table.Th>
                <Table.Th>trend</Table.Th><Table.Th>behaviour</Table.Th><Table.Th>acted</Table.Th>
              </Table.Head>
              <Table.Body>
                {rows.map((g) => (
                  <Table.Row key={g.name} onClick={() => open(g.name)} className={selected === g.name ? "selected" : undefined}>
                    <GoalCells g={{ ...g, behaviour: word(g.name, g) }} columns={COLUMNS} open={open} at={at} />
                  </Table.Row>
                ))}
              </Table.Body>
            </Table>
          );
        }}
      </Async>
      {w && <Note>Time off and back in: {w}. Back in: typically, from going off to holding again.</Note>}
    </Page>
  );
}
