import { Fragment, useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { AppLink, Button, Check, EventsTable, Filters, Page, type RecordEvent } from "../../components";
import { useApi } from "../../hooks/useApi";
import { ApiError } from "../../lib/api";
import { dur, stamp } from "../../lib/format";

/* The Record: the events, newest first, a run of identical ones folded. The filter (match=: an event's type, item or
   source) and the scope (machine=, item=, about=, from=, to=, remote=, and window=1: only the page's window) stay in
   the address, so a link opens the same view; a sensor's observations and a goal's crossing link here. The old page's
   pageRecord (pages.js).

   window=1 is the old page's own "in the window" mode: the shared time window is ``window=`` too, so with window=1 the
   window shown is the default hour, and choosing another window in the header replaces the scope. */

const SCOPE = ["about", "from", "to", "machine", "item", "remote"] as const;

export default function RecordPage() {
  const [q, setQ] = useSearchParams();
  const match = q.get("match") || q.get("filter") || q.get("type") || "";
  const runs = q.get("runs") === "1";
  const inWindow = q.get("window") === "1";
  const scope = Object.fromEntries(SCOPE.map((k) => [k, q.get(k) || ""])) as Record<(typeof SCOPE)[number], string>;
  const [typed, setTyped] = useState(match);
  useEffect(() => setTyped(match), [match]);

  const set = (changes: Record<string, string>) =>
    setQ((p) => {
      const n = new URLSearchParams(p);
      n.delete("filter");
      n.delete("type");
      for (const [k, v] of Object.entries(changes)) {
        if (v) n.set(k, v);
        else n.delete(k);
      }
      return n;
    }, { replace: true });
  const apply = (v = typed) => set({ match: v.trim() });

  const remotes = useApi<any>("items", { n: 1 }, { window: false });
  const scoped = inWindow || SCOPE.some((k) => scope[k]);
  const scopeWords: ReactNode[] = [
    scope.item && `about ${scope.item}`,
    scope.about && `of goal ${scope.about}`,
    scope.machine && <>from <AppLink className="agent-link" to={`/agent/${encodeURIComponent(scope.machine)}`}>{scope.machine}</AppLink></>,
    scope.remote && `of remote ${scope.remote}`,
    inWindow && "in the window",
    scope.from && `from ${stamp(+scope.from)}`,
    scope.to && `to ${stamp(+scope.to)}`,
  ].filter(Boolean);

  return (
    <Page title="Record">
      <Filters>
        <input
          type="search"
          placeholder="Type, item or source, e.g. valve.* or fixer"
          aria-label="Event type, item or source"
          value={typed}
          onChange={(ev) => setTyped(ev.target.value)}
          onKeyDown={(ev) => { if (ev.key === "Enter") apply(); }}
        />
        <Button onClick={() => apply()}>Filter</Button>
        {scoped && (
          <span className="muted">
            {scopeWords.map((x, i) => <Fragment key={i}>{i ? ", " : ""}{x}</Fragment>)}{" "}
            <AppLink to={"/record" + (match ? "?match=" + encodeURIComponent(match) : "")}>Show all</AppLink>
          </span>
        )}
        <span className="remote-links">
          {(remotes.data?.remotes || []).map((r: any) => (
            <AppLink
              key={r.name}
              className={r.name === scope.remote ? "on" : ""}
              to={`/record?remote=${encodeURIComponent(r.name)}`}
              title={`${r.url}: its events, read there`}
            >
              {`remote ${r.name}`}
            </AppLink>
          ))}
        </span>
        <Check
          label={<>Show runs <span className="muted">(agent.started, agent.ran)</span></>}
          checked={runs}
          onChange={(ev) => set({ runs: ev.target.checked ? "1" : "" })}
        />
      </Filters>
      {scope.remote ? (
        <RemoteEvents remote={scope.remote} match={match} onClear={() => apply("")} />
      ) : (
        <LocalEvents match={match} runs={runs} inWindow={inWindow} scope={scope} onClear={() => apply("")} />
      )}
    </Page>
  );
}

function Nothing({ match, onClear }: { match: string; onClear: () => void }) {
  if (!match) return <p className="muted">Nothing recorded yet.</p>;
  return (
    <p className="muted">
      {`Nothing matches “${match}” · `}
      <a href="#" className="clear-filter" onClick={(ev) => { ev.preventDefault(); onClear(); }}>clear</a>
    </p>
  );
}

function LocalEvents({ match, runs, inWindow, scope, onClear }: {
  match: string; runs: boolean; inWindow: boolean; scope: Record<string, string>; onClear: () => void;
}) {
  const { remote: _r, ...asked } = scope;
  const params = Object.fromEntries(
    Object.entries({ match, runs: runs ? "1" : "", window: inWindow ? "1" : "", ...asked }).filter(([, v]) => v),
  );
  const evs = useApi<RecordEvent[]>("events", { n: 80, ...params }, { every: 3000 });
  if (evs.data === undefined) return evs.error ? <p className="muted">{evs.error.message}</p> : <p className="muted">Loading…</p>;
  if (evs.error) return <p className="muted">{evs.error.message}</p>;
  return evs.data.length ? <EventsTable events={evs.data} fold /> : <Nothing match={match} onClear={onClear} />;
}

/* a remote's events (SPEC §4c), read there: what failed said, with how old what is shown is; never "nothing" */
function RemoteEvents({ remote, match, onClear }: { remote: string; match: string; onClear: () => void }) {
  const r = useApi<any>("events", { remote, n: 80, ...(match ? { type: match } : {}) }, { every: 3000, window: false });
  if (r.data === undefined && !r.error) return <p className="muted">Loading…</p>;
  const d = r.error
    ? { failed: true, code: r.error instanceof ApiError ? r.error.status : undefined, why: r.error.message }
    : r.data;
  const old = d.read != null ? `; these were read ${dur(d.age)} ago` : "";
  const said = d.failed || !d.ok
    ? <p className="note remote-says bad">{d.code === 503 ? `${remote}: ${d.why}` : `${remote} does not answer (${d.why})${old}`}</p>
    : d.why ? <p className="note remote-says">{`${d.why}${old}`}</p> : null;
  const list = d.failed ? null : d.events?.length ? <EventsTable events={d.events} fold /> : d.ok ? <Nothing match={match} onClear={onClear} /> : null;
  return <>{said}{list}</>;
}
