import type { RecordEvent } from "../../events";
import { crossingsTitle, decisionsTitle, GoalCrossings, GoalDecisions } from "../../goalRecord";
import { RecordEvents, RemoteEvents } from "../../recordEvents";
import { Async } from "../../ui";
import type { PanelBodyProps, PanelKind } from "../types";
import { usePanelApi } from "../usePanelApi";
import { paramsOf } from "./core";

/* The record group's kinds of panel (each also declared in ergostat/spec/dashboards.py, its record block):
   - events: the record's events (GET /api/events), newest first, a run of identical ones folded, a click showing an
     event in the side panel; `system` only those behind what that system contains ("" every one); `remote` names a
     remote whose events are shown instead, read there (SPEC §4c);
   - goal-crossings, goal-decisions: what a goal's loop recorded in the window (GET /api/loops/{goal}). */

/** What an events panel asks GET /api/events, by the endpoint's own names (none: its newest 80). */
export const EVENTS_PARAMS = ["match", "item", "about", "machine", "runs", "window", "from", "to", "n", "system"] as const;

const wrap = (def: PanelBodyProps["def"]) => (def.fit ? "panel-events" : "panel-table panel-events");

function LocalEventsBody({ def, every, refreshKey }: PanelBodyProps) {
  const asked = paramsOf(def, ...EVENTS_PARAMS);
  const got = usePanelApi<RecordEvent[]>("events", { n: 80, ...asked }, every, refreshKey);
  return <div className={wrap(def)}><RecordEvents got={got} match={def.match} scope={asked} /></div>;
}

function RemoteEventsBody({ def, every, refreshKey }: PanelBodyProps) {
  const got = usePanelApi<any>("events", { n: 80, ...paramsOf(def, "remote", "match", "n") }, every, refreshKey);
  return <div className={wrap(def)}><RemoteEvents remote={String(def.remote)} got={got} match={def.match} /></div>;
}

function EventsBody(p: PanelBodyProps) {
  return p.def.remote ? <RemoteEventsBody {...p} /> : <LocalEventsBody {...p} />;
}

function useLoop({ def, every, refreshKey }: PanelBodyProps) {
  return usePanelApi<any>(def.goal ? `loops/${encodeURIComponent(def.goal)}` : null, {}, every, refreshKey);
}

function CrossingsBody(p: PanelBodyProps) {
  const lp = useLoop(p);
  const goal = String(p.def.goal || "");
  if (!goal) return <p className="note lvl-error">A goal-crossings panel needs goal:.</p>;
  return (
    <div className="panel-table">
      <Async state={lp} what="Its crossings">
        {(d) => d?.crossings?.length ? (
          <>
            {!p.def.title && <p className="muted small">{crossingsTitle(d)}</p>}
            <GoalCrossings goal={goal} lp={d} />
          </>
        ) : <p className="muted">{d ? `${goal} did not cross its bound in the window.` : `${goal} is not a goal.`}</p>}
      </Async>
    </div>
  );
}

function DecisionsBody(p: PanelBodyProps) {
  const lp = useLoop(p);
  const goal = String(p.def.goal || "");
  if (!goal) return <p className="note lvl-error">A goal-decisions panel needs goal:.</p>;
  return (
    <div className="panel-table">
      <Async state={lp} what="Its decisions">
        {(d) => d?.decisions?.count ? (
          <>
            {!p.def.title && <p className="muted small">{decisionsTitle(d)}</p>}
            <GoalDecisions goal={goal} lp={d} most={p.def.fit ? 50 : 12} />
          </>
        ) : <p className="muted">{d ? `${goal}'s controller decided nothing in the window.` : `${goal} is not a goal.`}</p>}
      </Async>
    </div>
  );
}

export const RECORD: Record<string, PanelKind> = {
  events: { label: "Events of the record", Body: EventsBody },
  "goal-crossings": { label: "A goal's crossings", needs: "goal", Body: CrossingsBody },
  "goal-decisions": { label: "A goal's decisions", needs: "goal", Body: DecisionsBody },
};
