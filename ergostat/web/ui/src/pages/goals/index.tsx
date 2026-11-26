import { useCallback, useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { ALL_COLUMNS, Async, GoalDetail, GoalsTable, Muted, Note, Page, PanelFrame, useDetail } from "../../components";
import { QuietSystems } from "../../components/Attention";
import { asQueryPanel, type PanelDef } from "../../components/panels";
import { useApi } from "../../hooks/useApi";
import { windowNote } from "../../lib/format";
import { goalsOff, useStatus } from "../../state/status";

/* Goals (the old pages.js pageLoops), a dashboard made in advance: the quiet-systems panel (when a system is quiet) and
   the goals panel, full width with every column, those that need someone first. A click opens the goal's detail beside
   the page, the goal chosen kept in the address (?select=NAME): the page's own, not the panel's. */

const QUIET: PanelDef = { panel: "quiet-systems", id: "quiet", title: "Quiet systems", size: "full", fit: true };
const GOALS: PanelDef = { panel: "goals", id: "goals", title: "Every goal", size: "full", fit: true };

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
      <div className="panel-grid">
        {(systems.data || []).some((s) => s.quiet) && (
          <PanelFrame panel={asQueryPanel(QUIET)} className="panel-kind-quiet-systems">
            <QuietSystems systems={systems.data || []} />
          </PanelFrame>
        )}
        <PanelFrame panel={asQueryPanel(GOALS)} className="panel-kind-goals">
          <div className="panel-table">
            <Async state={loops}>
              {(data) => <GoalsTable loops={data} columns={ALL_COLUMNS} selected={selected} onOpen={open} caption={GOALS.title} />}
            </Async>
          </div>
        </PanelFrame>
      </div>
      {w && <Note>Time off and back in: {w}. Back in: typically, from going off to holding again.</Note>}
    </Page>
  );
}
