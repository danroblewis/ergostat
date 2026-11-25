import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Async, Empty, Filters, Note, Page } from "../../components";
import { useApi } from "../../hooks/useApi";
import { FlowChart, ItemsTable, KindBar, hiddenStates, kindHref, plural } from "./parts";

/* /items: the overview of kinds (kinds.js pageKinds) when the address has only ?states= or the window; /items?kind=K
   goes to the kind's page; a search or any other filter lists every kind's items (pages.js pageItems). */

const OVERVIEW_KEYS = new Set(["states", "window", "at"]);

export default function ItemsPage() {
  const [q] = useSearchParams();
  const kind = q.get("kind");
  if (kind) {
    const rest = new URLSearchParams(q);
    rest.delete("kind");
    const s = rest.toString();
    return <Navigate replace to={kindHref(kind) + (s ? `?${s}` : "")} />;
  }
  const overview = [...q.keys()].every((k) => OVERVIEW_KEYS.has(k));
  return overview ? <Overview /> : <EveryKind />;
}

const perHour = (x: number | null | undefined) =>
  x == null ? "–" : x >= 10 ? String(Math.round(x)) : x >= 1 ? x.toFixed(1) : x ? x.toFixed(2) : "0";

function Search({ value, onSearch, live }: { value?: string; onSearch: (w: string) => void; live?: boolean }) {
  const [text, setText] = useState(value ?? "");
  return (
    <input
      type="search"
      placeholder="Search kinds, ids and fields"
      aria-label="Search"
      value={text}
      onChange={(ev) => { setText(ev.target.value); if (live) onSearch(ev.target.value); }}
      onKeyDown={(ev) => { if (ev.key === "Enter") onSearch(text.trim()); }}
    />
  );
}

/** The overview: under each system, a card per kind with its counts, rates and its states over the window. */
function Overview() {
  const [q, setQ] = useSearchParams();
  const navigate = useNavigate();
  const all = q.get("states") === "all";
  const state = useApi<any>("items-overview", {}, { every: 15000 });
  const pick = (to: boolean) => setQ((p) => { const n = new URLSearchParams(p); if (to) n.set("states", "all"); else n.delete("states"); return n; }, { replace: true });
  return (
    <Page title="Items">
      <Filters>
        <Search onSearch={(w) => w && navigate(`/items?q=${encodeURIComponent(w)}`)} />
        <span className="rg-viewbar">
          <span className="seg" role="group" aria-label="States">
            <button type="button" className={!all ? "on" : ""} aria-pressed={!all} title="Each kind's states as waiting, working, stopped and done" onClick={() => pick(false)}>State groups</button>
            <button type="button" className={all ? "on" : ""} aria-pressed={all} title="Each kind's own states" onClick={() => pick(true)}>Every state</button>
          </span>
        </span>
        <Link to="/items?view=list" className="small">every kind's list</Link>
      </Filters>
      <div className="kind-overview">
        <Async state={state}>
          {(d) => {
            const kindOf: Record<string, any> = Object.fromEntries(d.kinds.map((k: any) => [k.name, k]));
            const quiet = d.kinds.filter((k: any) => k.quiet);
            return (
              <>
                {d.systems.map((g: any) => {
                  const ks = g.kinds.map((n: string) => kindOf[n]).filter((k: any) => k && !k.quiet);
                  if (!ks.length) return null;
                  const n = ks.reduce((a: number, k: any) => a + (k.total || 0), 0);
                  return (
                    <section key={g.name} className="sys-group" data-system={g.name}>
                      <h2 className="sys-head">
                        {g.name}
                        <span className="muted"> {plural(n, "item")}, {plural(ks.length, "kind")}</span>
                        {g.description && <span className="muted sys-desc">{g.description}</span>}
                      </h2>
                      <div className="kind-cards">
                        {ks.map((k: any) => <KindCard key={k.name} k={k} d={d} all={all} />)}
                      </div>
                    </section>
                  );
                })}
                {quiet.length > 0 && (
                  <p className="muted kinds-quiet">
                    Nothing in the window:{" "}
                    {quiet.map((k: any, i: number) => (
                      <span key={k.name}>{i ? ", " : ""}<Link to={kindHref(k.name)}>{k.title || k.name}</Link></span>
                    ))}
                  </p>
                )}
                {d.unkinded > 0 && <Note>{plural(d.unkinded, "item")} match no kind of the model's.</Note>}
                {!d.kinds.length && <Empty>No items yet. An item is what events with an id like ticket/12 are about (ergostat help spec).</Empty>}
              </>
            );
          }}
        </Async>
      </div>
    </Page>
  );
}

function KindCard({ k, d, all }: { k: any; d: any; all: boolean }) {
  const href = kindHref(k.name);
  const states: string[] = all ? k.states : d.groups.filter((g: string) => k.by_group && g in k.by_group);
  return (
    <div className="kind-flow kind-card" data-kind={k.name}>
      <Link to={href} className="kname">
        {k.title || k.name}
        <span className="mono">{k.title ? k.name : k.id}</span>
      </Link>
      <a className="pm-link" href={`/diagram?view=process&kind=${encodeURIComponent(k.name)}&mode=states`}
        title="Its process map: how many are in each state now, and how they moved">process map</a>
      {k.why ? (
        <div className="kind-counts muted small">{k.why}</div>
      ) : (
        <div className="kind-counts small">
          <b>{k.unfinished}</b>
          <span className="muted"> unfinished of {k.total}</span>
          <span className="muted" title={`arrived in the window: ${k.arrived}; finished: ${k.left ?? "–"}`}>
            {" "}· in {perHour(k.rate_in)}/h, out {perHour(k.rate_out)}/h
          </span>
        </div>
      )}
      {k.counts && (
        <FlowChart times={d.times} states={states} counts={all ? k.counts : k.by_group} height={64} xAxis={false} />
      )}
    </div>
  );
}

/** Every kind's items (/items?view=list, or a search): under each system, each kind's newest, matched to the search. */
function EveryKind() {
  const [q, setQ] = useSearchParams();
  const needle = (q.get("q") || "").trim();
  const showFin = q.get("finished") === "show";
  const state = useApi<any>("items", {
    per_kind: 25, shown: 1, ...(needle ? { q: needle } : {}), ...(showFin ? { finished: "show" } : {}),
  }, { every: 10000 });
  const set = (k: string, v: string | null) =>
    setQ((p) => { const n = new URLSearchParams(p); if (v) n.set(k, v); else n.delete(k); if (!n.toString()) n.set("view", "list"); return n; }, { replace: true });
  return (
    <Page title="Items">
      <Filters>
        <Search value={needle} live onSearch={(w) => set("q", w.trim() || null)} />
        <span className="fin-choice">
          <span className="muted">Finished items:</span>
          <span className="seg fin-seg" role="group" aria-label="Finished items">
            <button type="button" className={!showFin ? "on" : ""} aria-pressed={!showFin} onClick={() => set("finished", null)}>Hidden</button>
            <button type="button" className={showFin ? "on" : ""} aria-pressed={showFin} onClick={() => set("finished", "show")}>Shown</button>
          </span>
        </span>
        <Link to="/items" className="small">the overview</Link>
      </Filters>
      <div className="item-systems">
        <Async state={state}>
          {(d) => <EveryKindBody d={d} needle={needle} showFin={showFin} />}
        </Async>
      </div>
    </Page>
  );
}

function EveryKindBody({ d, needle, showFin }: { d: any; needle: string; showFin: boolean }) {
  const kindOf: Record<string, any> = Object.fromEntries(d.kinds.map((k: any) => [k.name, k]));
  const hits: Record<string, number> | null = needle ? d.matched || {} : null;
  const hitsN = hits ? Object.values(hits).reduce((a, b) => a + b, 0) : 0;
  const systems = d.systems || [{ name: "", kinds: d.kinds.map((k: any) => k.name) }];
  return (
    <>
      {needle && <p className="muted search-hits" aria-live="polite">{hitsN ? `${hitsN} match${hitsN === 1 ? "" : "es"}` : "nothing matches"}</p>}
      {d.unkinded > 0 && <Note>{plural(d.unkinded, "item")} match no kind of the model's; shown with their fields, no state.</Note>}
      {!d.kinds.length && !d.unkinded && <Empty>No items yet. An item is what events with an id like ticket/12 are about (ergostat help spec).</Empty>}
      {systems.map((g: any) => {
        const names: string[] = [...g.kinds, ...(g.name === "other" && d.unkinded ? [""] : [])];
        if (hits && !names.some((n) => hits[n] > 0)) return null;
        const parts = names.map((name) => {
          const its = d.items.filter((i: any) => (i.kind || "") === name);
          const k = kindOf[name];
          const left = hiddenStates(k).filter((s) => k?.counts?.[s]);
          const nLeft = left.reduce((a, s) => a + k.counts[s], 0);
          if (!its.length && !(nLeft && !showFin && !needle)) return null;
          return (
            <div key={name || "-"}>
              <h3 className="kind-head">
                {k ? <Link to={kindHref(name)}>{k.title || name}</Link> : "No kind"}
                {k?.title && <span className="muted small mono"> {name}</span>}
                <span className="muted"> {d.matched?.[name] ?? its.length}</span>
              </h3>
              {its.length > 0 && <ItemsTable items={its} show={k?.show || []} caption={`${name || "No kind"} items`} />}
              {nLeft > 0 && !showFin && !needle && <p className="note finished-note">{nLeft} finished ({left.join(", ")}) not shown</p>}
            </div>
          );
        }).filter(Boolean);
        if (!parts.length) return null;
        return (
          <section key={g.name} className="sys-group" data-system={g.name}>
            <h2 className="sys-head">
              {g.name}
              <span className="muted"> {plural(g.kinds.length, "kind")}</span>
              {g.description && <span className="muted sys-desc">{g.description}</span>}
            </h2>
            {parts}
          </section>
        );
      })}
    </>
  );
}

