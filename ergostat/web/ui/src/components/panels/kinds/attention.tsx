import { useCallback, type ReactNode } from "react";
import { PanelFrame } from "../../charts/PanelView";
import { Attention, ControlLoops, FeedbackLoops, feedbackCount, Legend, LEGEND_TYPE, QuietSystems, type AttentionPart } from "../../Attention";
import { Decisions, type Entry } from "../../Decisions";
import { useDetail } from "../../Detail";
import { GoalDetail } from "../../GoalDetail";
import { GoalControl, GoalParts, GoalRunbook } from "../../GoalParts";
import { Async } from "../../ui";
import { scopedBy } from "../../../lib/scoped";
import { projectionsOfId } from "../../../lib/routes";
import { useDashboards } from "../../../state/dashboards";
import { useStatus } from "../../../state/status";
import type { PanelBodyProps, PanelKind } from "../types";
import { usePanelApi } from "../usePanelApi";
import { asQueryPanel, paramsOf } from "./core";

/* The attention group's kinds of panel (each also declared in ergostat/spec/dashboards.py, its attention block): what
   asks for the owner, how to read a drawing, the loops a view draws, the quiet systems, and one goal's runbook, parts
   and control loop. A goal named in any of them opens its detail beside the page, as the goals panel's rows do. */

const listOf = (v: unknown): string[] | null =>
  Array.isArray(v) ? v.map(String) : typeof v === "string" && v ? v.split(",").map((x) => x.trim()).filter(Boolean) : null;

function useOpenGoal() {
  const detail = useDetail();
  return useCallback((name: string) => detail.open(`goal:${name}`, <GoalDetail key={name} name={name} />), [detail]);
}

/** /api/status's attention, as the app already asks it every 5 s (state/status.tsx): never asked twice. `system`:
 *  what is about a part that system contains (its goals, its agents, its projections' items); what names no part is
 *  the top level's. */
function AttentionBody({ def }: PanelBodyProps) {
  const { status } = useStatus();
  const onGoal = useOpenGoal();
  const s = scopedBy(useDashboards().table, def.system);
  const about = (a: any) => !s || (a.goal ? s.has("goals", a.goal)
    : a.item ? projectionsOfId(String(a.item)).some((k) => s.has("projections", k.name)) || s.system === ""
    : a.block || a.agent ? s.has("agents", a.block || a.agent) : s.system === "");
  return (
    <div className="panel-table">
      <Attention attention={(status?.attention || []).filter(about)} status={status} show={listOf(def.show) as AttentionPart[] | null} onGoal={onGoal} />
    </div>
  );
}

/** What waits on a person (GET /api/inbox: what `ergostat inbox` lists), each a card answered in place. `kinds`: only
 *  those kinds of entry (action, person, advise, steptest, change, request, breaker); `system`: those about a part it
 *  contains (a block's, or a request's part's system), the top level all of them. */
function DecisionsBody({ def, every, refreshKey }: PanelBodyProps) {
  const got = usePanelApi<{ entries: Entry[] }>("inbox", {}, every ?? 5000, refreshKey);
  const { table } = useDashboards();
  const s = scopedBy(table, def.system);
  const kinds = listOf(def.kinds);
  const within = (x: string | null | undefined): boolean => {   // the system, or one within it
    for (let at = x; at; at = table?.scopes[at]?.within) if (at === s?.system) return true;
    return false;
  };
  const about = (e: Entry) => !s || s.system === "" || (e.block ? s.has("agents", e.block) : within(e.system));
  return (
    <div className="panel-table">
      <Async state={got}>{(d) => <Decisions entries={(d?.entries || []).filter((e) => (!kinds?.length || kinds.includes(e.kind)) && about(e))} />}</Async>
    </div>
  );
}

function LegendBody({ def }: PanelBodyProps) {
  return (
    <div className="panel-table">
      <p className="muted small">How to read the {LEGEND_TYPE[def.view] || def.view}.</p>
      <Legend view={def.view} />
    </div>
  );
}

function FeedbackLoopsBody({ def, every, refreshKey }: PanelBodyProps) {
  const g = usePanelApi<any>("graph", { view: "dynamics", ...paramsOf(def, "system") }, every, refreshKey);
  return (
    <div className="panel-table">
      <Async state={g}>{(d) => <><p className="muted small">{feedbackCount(d)}</p><FeedbackLoops g={d} /></>}</Async>
    </div>
  );
}

function ControlLoopsBody({ def, every, refreshKey }: PanelBodyProps) {
  const g = usePanelApi<any>("graph", { view: "blocks", ...paramsOf(def, "system") }, every, refreshKey);
  const onGoal = useOpenGoal();
  return <div className="panel-table"><Async state={g}>{(d) => <ControlLoops g={d} onGoal={onGoal} />}</Async></div>;
}

/** The quiet systems; `quiet` (a page's): not drawn at all while no system is quiet. */
function QuietSystemsFrame({ def, every, refreshKey, tools }: PanelBodyProps & { tools?: ReactNode }) {
  const systems = usePanelApi<any[]>("systems", {}, every, refreshKey);
  if (def.quiet && !(systems.data || []).some((s) => s.quiet)) return null;
  return (
    <PanelFrame panel={asQueryPanel(def)} tools={tools} className="panel-kind-quiet-systems">
      <div className="panel-table">
        <Async state={systems}>{(d) => <QuietSystems systems={d} none={<p className="muted">No system is quiet now.</p>} />}</Async>
      </div>
    </PanelFrame>
  );
}

const goalPath = (def: PanelBodyProps["def"]) => (def.goal ? `loops/${encodeURIComponent(def.goal)}` : null);

function GoalRunbookBody({ def, every, refreshKey }: PanelBodyProps) {
  const lp = usePanelApi<any>(goalPath(def), {}, every, refreshKey);
  return <div className="panel-table"><Async state={lp} what="Goal">{(d) => <GoalRunbook name={def.goal} lp={d} />}</Async></div>;
}

function GoalPartsBody({ def, every, refreshKey }: PanelBodyProps) {
  const lp = usePanelApi<any>(goalPath(def), {}, every, refreshKey);
  return <div className="panel-table"><Async state={lp} what="Goal">{(d) => <GoalParts name={def.goal} lp={d} />}</Async></div>;
}

function GoalControlBody({ def, every, refreshKey }: PanelBodyProps) {
  const ctl = usePanelApi<any>(def.goal ? "loop-control" : null, paramsOf(def, "goal"), every, refreshKey);
  const { status } = useStatus();
  return <div className="panel-table"><GoalControl ctl={ctl} off={status?.loops?.[def.goal]?.off_share} /></div>;
}

export const ATTENTION: Record<string, PanelKind> = {
  attention: { label: "What asks for you", Body: AttentionBody },
  decisions: { label: "Decisions waiting for you", Body: DecisionsBody },
  legend: { label: "How to read a view", needs: "view", Body: LegendBody },
  "feedback-loops": { label: "Feedback loops", Body: FeedbackLoopsBody },
  "control-loops": { label: "Control loops", Body: ControlLoopsBody },
  "quiet-systems": { label: "Quiet systems", Frame: QuietSystemsFrame },
  "goal-runbook": { label: "A goal's runbook", needs: "goal", Body: GoalRunbookBody },
  "goal-parts": { label: "A goal's parts along its loop", needs: "goal", Body: GoalPartsBody },
  "goal-control": { label: "A goal's control loop", needs: "goal", Body: GoalControlBody },
};
