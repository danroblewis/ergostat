import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { AppLink, Button, Check, Filters, Page } from "../../components";
import { DashboardView, type PanelDef } from "../../components/panels";
import { useApi } from "../../hooks/useApi";
import { stamp } from "../../lib/format";

/* The Record, a dashboard made by ergostat: one events panel (panels/kinds/record.tsx) as tall as what it shows, its
   parameters the address's. The filter (match=: an event's type, item or source), the scope (machine=, item=, about=,
   from=, to=, remote=, and window=1: only the page's window) and runs=1 stay in the address, so a link opens the same
   view; a sensor's observations and a goal's crossing link here. The filter bar, the scope's words, the remotes'
   links and "Show runs" are the page's own, around the panel.

   window=1 is the old page's own "in the window" mode: the shared time window is ``window=`` too, so with window=1 the
   window shown is the default hour, and choosing another window in the header replaces the scope. */

const SCOPE = ["about", "from", "to", "machine", "item", "remote"] as const;
const EVERY = 3000;          // ms: the record is asked again this often

/** The Record's one panel, from the address's words. */
function recordPanel(match: string, runs: boolean, inWindow: boolean, scope: Record<string, string>): PanelDef {
  const { remote, from, to, ...rest } = scope;
  const named = Object.fromEntries(Object.entries(rest).filter(([, v]) => v));
  const time = (v: string) => (v && Number.isFinite(+v) ? +v : undefined);
  return remote
    ? { panel: "events", id: "record", title: `The events of remote ${remote}, newest first`, size: "full", fit: true, remote, ...(match ? { match } : {}) }
    : {
      panel: "events", id: "record", title: "Events, newest first", size: "full", fit: true, ...named,
      ...(match ? { match } : {}), ...(runs ? { runs: true } : {}), ...(inWindow ? { window: true } : {}),
      ...(time(from) != null ? { from: time(from) } : {}), ...(time(to) != null ? { to: time(to) } : {}),
    };
}

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
  const key = JSON.stringify([match, runs, inWindow, scope]);
  const panels = useMemo(() => [recordPanel(match, runs, inWindow, scope)], [key]); // eslint-disable-line react-hooks/exhaustive-deps

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
      <DashboardView panels={panels} every={EVERY} />
    </Page>
  );
}
