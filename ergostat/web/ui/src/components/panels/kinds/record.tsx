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
     remote whose events are shown instead, read there (SPEC §4c); `query` the event query (plain words a full-text
     search, else an expression of the event, unexplained() the events no projection takes: SPEC §5a), read through
     its index, its count and how it was read said above the events;
   - goal-crossings, goal-decisions: what a goal's loop recorded in the window (GET /api/loops/{goal}). */

/** What an events panel asks GET /api/events, by the endpoint's own names (none: its newest 80). */
export const EVENTS_PARAMS = ["match", "query", "item", "about", "machine", "runs", "window", "from", "to", "n", "system"] as const;

const wrap = (def: PanelBodyProps["def"]) => (def.fit ? "panel-events" : "panel-table panel-events");

/** A query's answer (GET /api/events?query=): its events, and how many matched and how they were read. */
interface Queried { events: RecordEvent[]; total: number; shown: number; scanned?: boolean; exact?: boolean; capped?: boolean;
  candidates?: number; walked?: number; unexplained?: string; dropped?: number; took_ms?: number }

function QuerySays({ a }: { a: Queried }) {
  const how = a.scanned ? `the newest ${a.walked ?? ""} events scanned: no part of the query is indexed`
    : a.exact ? "from the index" : `${a.candidates ?? 0} candidates from the index, each evaluated`;
  return (
    <>
      {a.unexplained && <p className="note" data-testid="events-unexplained-note">{a.unexplained}</p>}
      <p className="muted small" data-testid="events-query-count">
        {`${a.total} event${a.total === 1 ? "" : "s"} match`}{a.shown < a.total ? `, the newest ${a.shown} shown` : ""}
        {` · ${how}${a.capped ? " (cut at the most it reads)" : ""}`}
        {a.dropped ? ` · ${a.dropped} a projection now takes left out` : ""}
      </p>
    </>
  );
}

function LocalEventsBody({ def, every, refreshKey }: PanelBodyProps) {
  const asked = paramsOf(def, ...EVENTS_PARAMS);
  const got = usePanelApi<RecordEvent[] | Queried>("events", { n: 80, ...asked }, every, refreshKey);
  const d = got.data;
  const queried = d && !Array.isArray(d) ? d : null;
  const listed = { data: queried ? queried.events : (d as RecordEvent[] | undefined), error: got.error };
  return (
    <div className={wrap(def)}>
      {queried && <QuerySays a={queried} />}
      <RecordEvents got={listed} match={(def.query as string | undefined) || def.match} scope={asked} />
    </div>
  );
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
