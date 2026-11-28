import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { AppLink, Button, Check, Filters, Muted, Page } from "../../components";
import { EditableDashboard, useEditing, type PanelDef } from "../../components/panels";
import { QueryEditor } from "../../components/query";
import { useApi } from "../../hooks/useApi";
import { stamp } from "../../lib/format";
import { agentHref, eventsHref } from "../../lib/hrefs";
import { pageDashboard } from "../../lib/pages";

/* A system's Events (/events for the top level, /SYSTEM/events), a dashboard made by ergostat: one events panel
   (panels/kinds/record.tsx) as tall as what it shows, its parameters the address's. An event has no system: a
   system's are those behind what it contains (its projections' items, its blocks' and agents' own: GET
   /api/events?system=, spec/routes.py events_of); the top level's are every event. The filter is the event query
   (q=: the workbench's box and language, eventquery.py: plain words a full-text search, `aws` has('aws'), else an
   expression of the event; "Unexplained only" puts unexplained() in it), read through its index (GET
   /api/events?query=). The old filter (match=: an event's type as a glob, item or source, exactly) still works, said
   among the scope's words. The scope (machine=, item=, about=, from=, to=, remote=, and window=1: only the page's
   window) and runs=1 stay in the address, so a link opens the same view; a sensor's observations and a goal's crossing
   link here. The filter bar, the scope's words, the remotes' links and "Show runs" are the page's own, around the
   panel.

   window=1 is the old page's own "in the window" mode: the shared time window is ``window=`` too, so with window=1 the
   window shown is the default hour, and choosing another window in the header replaces the scope.

   Edited in place, it is saved as the dashboard named events of that system (its panels as ergostat's, without the
   address's filter), drawn here in place of this page. */

const BASE = pageDashboard("events");

const SCOPE = ["about", "from", "to", "machine", "item", "remote"] as const;
const EVERY = 3000;          // ms: the record is asked again this often

/** The events panel's parameters, from the address's words. */
function eventsParams(match: string, query: string, runs: boolean, inWindow: boolean, scope: Record<string, string>): Record<string, unknown> {
  const { remote, from, to, ...rest } = scope;
  const named = Object.fromEntries(Object.entries(rest).filter(([, v]) => v));
  const time = (v: string) => (v && Number.isFinite(+v) ? +v : undefined);
  return remote
    ? { title: `The events of remote ${remote}, newest first`, remote, ...(match ? { match } : {}) }
    : {
      ...named, ...(match ? { match } : {}), ...(query ? { query } : {}), ...(runs ? { runs: true } : {}),
      ...(inWindow ? { window: true } : {}),
      ...(time(from) != null ? { from: time(from) } : {}), ...(time(to) != null ? { to: time(to) } : {}),
    };
}

const WORD = /^[^\s'"()[\]=!<>+*,]+$/;
const KEYWORDS = new Set(["and", "or", "not", "in", "is", "if", "else"]);
const UNEXPLAINED = /\bunexplained\(\s*\)/;

/** The box's text as the event query reads it (eventquery.as_query): plain words a full-text search, all of them. */
export function asQuery(text: string): string {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length && words.every((w) => WORD.test(w) && !KEYWORDS.has(w.toLowerCase()))) {
    return words.map((w) => `has('${w.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}')`).join(" and ");
  }
  return text.trim();
}

/** The query with unexplained() in it (on) or taken out (off): "Unexplained only". */
export function withUnexplained(text: string, on: boolean): string {
  const t = text.trim();
  if (on) {
    if (UNEXPLAINED.test(t)) return t;
    if (!t) return "unexplained()";
    const q = asQuery(t);
    return `unexplained() and ${/\bor\b/.test(q) ? `(${q})` : q}`;
  }
  return t.replace(/^unexplained\(\s*\)\s+and\s+/, "").replace(/\s+and\s+unexplained\(\s*\)/, "")
    .replace(/^unexplained\(\s*\)$/, "").trim();
}

export default function EventsPage({ system = "" }: { system?: string }) {
  const [q, setQ] = useSearchParams();
  const match = q.get("match") || q.get("filter") || q.get("type") || "";
  const query = q.get("q") || "";
  const runs = q.get("runs") === "1";
  const inWindow = q.get("window") === "1";
  const scope = Object.fromEntries(SCOPE.map((k) => [k, q.get(k) || ""])) as Record<(typeof SCOPE)[number], string>;
  const [typed, setTyped] = useState(query);
  useEffect(() => setTyped(query), [query]);

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
  const apply = (v = typed) => set({ q: v.trim() });
  const unexplainedOnly = UNEXPLAINED.test(query);

  const remotes = useApi<any>("items", { n: 1 }, { window: false });
  const scoped = inWindow || !!match || SCOPE.some((k) => scope[k]);
  const scopeWords: ReactNode[] = [
    match && `matching ${match}`,
    scope.item && `about ${scope.item}`,
    scope.about && `of goal ${scope.about}`,
    scope.machine && <>from <AppLink className="agent-link" to={agentHref(scope.machine)}>{scope.machine}</AppLink></>,
    scope.remote && `of remote ${scope.remote}`,
    inWindow && "in the window",
    scope.from && `from ${stamp(+scope.from)}`,
    scope.to && `to ${stamp(+scope.to)}`,
  ].filter(Boolean);
  const key = JSON.stringify([match, query, runs, inWindow, scope]);
  // the address's filter, given to ergostat's own events panel (its words and size are the dashboard's)
  const own = useMemo(() => eventsParams(match, query, runs, inWindow, scope), [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const ed = useEditing({ base: BASE, target: { name: "events", system }, bind: { system } });
  const decorate = useMemo(() => (d: PanelDef) => (d.id === "events" && d.panel === "events"
    ? { ...d, ...own, ...(own.remote ? { system: undefined } : {}) } : d), [own]);

  return (
    <Page title={<>Events{system && <Muted>{` · behind what ${system} contains`}</Muted>}</>}>
      <div className="page-edit">{ed.bar}</div>
      <Filters>
        <div className="events-query">
          <QueryEditor source="expression" value={typed} onChange={setTyped} onSubmit={(v) => apply(v)}
            label="Filter the events: words, or an expression of the event"
            placeholder="aws · or source == 'ec2-feed' and data.detail.state == 'running' · unexplained()" />
        </div>
        <Button onClick={() => apply()}>Filter</Button>
        <Check
          label="Unexplained only"
          checked={unexplainedOnly}
          onChange={(ev) => { const v = withUnexplained(typed || query, ev.target.checked); setTyped(v); apply(v); }}
        />
        {scoped && (
          <span className="muted">
            {scopeWords.map((x, i) => <Fragment key={i}>{i ? ", " : ""}{x}</Fragment>)}{" "}
            <AppLink to={eventsHref(query ? "q=" + encodeURIComponent(query) : "", system)}>Show all</AppLink>
          </span>
        )}
        <span className="remote-links">
          {(remotes.data?.remotes || []).map((r: any) => (
            <AppLink
              key={r.name}
              className={r.name === scope.remote ? "on" : ""}
              to={eventsHref(`remote=${encodeURIComponent(r.name)}`, system)}
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
      <EditableDashboard ed={ed} every={EVERY} decorate={decorate} />
    </Page>
  );
}
