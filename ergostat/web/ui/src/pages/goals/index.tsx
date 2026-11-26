import { useCallback, useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { Async, GoalDetail, GoalsTable, Muted, Note, Page, useDetail } from "../../components";
import { useApi } from "../../hooks/useApi";
import { windowNote } from "../../lib/format";
import { goalsOff, useStatus } from "../../state/status";

/* Goals (the old pages.js pageLoops): every goal, those that need someone first; a click opens its detail beside the
   page, the goal chosen kept in the address (?select=NAME). */

export default function GoalsPage() {
  const loops = useApi<Record<string, any>>("loops", { perf: 1 }, { every: 3000 });
  const systems = useApi<any[]>("systems", {}, { every: 3000 });
  const { status } = useStatus();
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
  const w = windowNote(status);

  return (
    <Page title={<>Goals{status && <Muted>{` · goals off ${off.off}${off.upkeep ? ` · model upkeep ${off.upkeep}` : ""}`}</Muted>}</>}>
      <div className="quiet-systems">
        {(systems.data || []).filter((s) => s.quiet).map((s) => (
          <p key={s.name} className="quiet-line" data-system={s.name}><b>{s.name}</b>: {s.quiet}</p>
        ))}
      </div>
      <Async state={loops}>
        {(data) => <GoalsTable loops={data} selected={selected} onOpen={open} />}
      </Async>
      {w && <Note>Time off and back in: {w}. Back in: typically, from going off to holding again.</Note>}
    </Page>
  );
}
