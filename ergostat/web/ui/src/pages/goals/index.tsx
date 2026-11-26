import { useCallback, useEffect, useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { GoalDetail, Muted, Note, Page, useDetail } from "../../components";
import { DashboardView } from "../../components/panels/DashboardView";
import { windowNote } from "../../lib/format";
import { GOALS_PANELS } from "../../lib/pages";
import { goalsOff, useStatus } from "../../state/status";

/* Goals (the old pages.js pageLoops), a dashboard made in advance (lib/pages.ts): the quiet-systems panel (drawn only
   when a system is quiet) and the goals panel, full width with every column. A click opens the goal's detail beside
   the page, the goal chosen kept in the address (?select=NAME): the page's own, handed to the panel. */

const EVERY = 3000;

export default function GoalsPage() {
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

  const panels = useMemo(() => GOALS_PANELS.map((d) => (d.panel === "goals" ? { ...d, onOpen: open, selected } : d)), [open, selected]);
  const off = goalsOff(status);
  const w = windowNote(status);

  return (
    <Page title={<>Goals{status && <Muted>{` · goals off ${off.off}${off.upkeep ? ` · model upkeep ${off.upkeep}` : ""}`}</Muted>}</>}>
      <DashboardView panels={panels} every={EVERY} />
      {w && <Note>Time off and back in: {w}. Back in: typically, from going off to holding again.</Note>}
    </Page>
  );
}
