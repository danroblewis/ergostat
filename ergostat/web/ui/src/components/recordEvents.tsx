import { useLocation } from "react-router-dom";
import { ApiError } from "../lib/api";
import { dur } from "../lib/format";
import { eventsHref } from "../lib/hrefs";
import { EventsTable, type RecordEvent } from "./events";
import { AppLink, Loading } from "./ui";

/* The record's events as the Record page and an events panel draw them (GET /api/events): folded runs, a click
   shows an event whole in the side panel; or a remote's events (SPEC §4c), read there, with what failed said and how
   old what is shown is, never "nothing". `got` is the answer's state, as useApi or usePanelApi gives it. */

type Got<T> = { data: T | undefined; error: Error | null };

/** Nothing to show: said so, and with a filter, a link to the Events without it (this address's, on an Events page;
 *  else the panel's system's). */
export function NothingRecorded({ match, scope = {} }: { match?: string; scope?: Record<string, unknown> }) {
  const here = useLocation();
  if (!match) return <p className="muted">Nothing recorded yet.</p>;
  const onEvents = /(^|\/)events\/?$/.test(here.pathname);
  const { system, ...rest0 } = scope;
  const q = new URLSearchParams(onEvents ? here.search
    : Object.entries(rest0).filter(([, v]) => v != null && v !== "" && v !== false).map(([k, v]) => [k, v === true ? "1" : String(v)]));
  q.delete("match");
  q.delete("filter");
  q.delete("type");
  const rest = q.toString();
  return (
    <p className="muted">
      {`Nothing matches “${match}” · `}
      <AppLink className="clear-filter" to={onEvents ? `${here.pathname}${rest ? `?${rest}` : ""}` : eventsHref(rest, typeof system === "string" ? system : "")}
        replace={onEvents}>clear</AppLink>
    </p>
  );
}

/** The record's own events, newest first. */
export function RecordEvents({ got, match, scope }: { got: Got<RecordEvent[]>; match?: string; scope?: Record<string, unknown> }) {
  if (got.data === undefined) return got.error ? <p className="muted">{got.error.message}</p> : <Loading />;
  if (got.error) return <p className="muted">{got.error.message}</p>;
  return got.data.length ? <EventsTable events={got.data} fold /> : <NothingRecorded match={match} scope={scope} />;
}

/** A remote's events, read there (its answer: {remote, ok, why, read, age, events}). */
export function RemoteEvents({ remote, got, match }: { remote: string; got: Got<any>; match?: string }) {
  if (got.data === undefined && !got.error) return <Loading />;
  const d = got.error
    ? { failed: true, code: got.error instanceof ApiError ? got.error.status : undefined, why: got.error.message }
    : got.data;
  const old = d.read != null ? `; these were read ${dur(d.age)} ago` : "";
  const said = d.failed || !d.ok
    ? <p className="note remote-says bad">{d.code === 503 ? `${remote}: ${d.why}` : `${remote} does not answer (${d.why})${old}`}</p>
    : d.why ? <p className="note remote-says">{`${d.why}${old}`}</p> : null;
  const list = d.failed ? null : d.events?.length ? <EventsTable events={d.events} fold />
    : d.ok ? <NothingRecorded match={match} scope={{ remote }} /> : null;
  return <>{said}{list}</>;
}
