import { useCallback, useEffect, useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { GoalDetail, Muted, Note, Page, useDetail } from "../../components";
import { EditableDashboard, useEditing } from "../../components/panels/EditableDashboard";
import { windowNote } from "../../lib/format";
import { pageDashboard } from "../../lib/pages";
import { goalsOff, useStatus } from "../../state/status";

/* Goals (the old pages.js pageLoops), a dashboard made in advance (lib/pages.ts): the quiet-systems panel (drawn only
   when a system is quiet) and the goals panel, full width with every column. A click opens the goal's detail beside
   the page, the goal chosen kept in the address (?select=NAME): the page's own, handed to the panel. Edited in place,
   it is saved as the dashboard named goals, drawn here in place of this page. */

const BASE = pageDashboard("goals");

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

  const ed = useEditing({ base: BASE, target: { name: "goals" } });
  const decorate = useMemo(() => (d: any) => (d.panel === "goals" ? { ...d, onOpen: open, selected } : d), [open, selected]);
  const off = goalsOff(status);
  const w = windowNote(status);

  return (
    <Page title={<>Goals{status && <Muted>{` · goals off ${off.off}${off.upkeep ? ` · model upkeep ${off.upkeep}` : ""}`}</Muted>}</>}>
      <div className="page-edit">{ed.bar}</div>
      <EditableDashboard ed={ed} every={EVERY} decorate={decorate} />
      {w && <Note>Time off and back in: {w}. Back in: typically, from going off to holding again.</Note>}
    </Page>
  );
}
