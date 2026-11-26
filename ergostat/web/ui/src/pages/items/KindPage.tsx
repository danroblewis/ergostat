import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Async, Button, Code, Empty, ErrorNote, Filters, FlowChart, Fold, ItemsTable, KindBar, Loading, Page, Select, StatusWord, hiddenStates } from "../../components";
import { useApi } from "../../hooks/useApi";
import { dur, plural } from "../../lib/format";

/* /items/KIND (pages.js pageItems with ``only``, kindpage.js): its bar as the page's heading (a state chip filters
   the list), Now (its states over the window and how long its finished took), In the model (what counts it, the
   goals and loops it is in), its definition, then its items, a page at a time, searched and sorted by the server.
   Every choice is in the address: state=, q=, finished=show, sort=KIND:field, page=KIND:N, size=, states=all. */

const SIZES = [25, 100, 300];

export default function KindPage() {
  const { kind = "" } = useParams();
  const [q, setQ] = useSearchParams();
  // a value for another kind (page=gap:3) is not this one's
  const ofKind = (v: string | null) => { const s = v || ""; const i = s.indexOf(":"); return i < 0 ? s : s.slice(0, i) === kind ? s.slice(i + 1) : ""; };
  const state = q.get("state");
  const needle = (q.get("q") || "").trim();
  const showFin = q.get("finished") === "show";
  const sort = ofKind(q.get("sort"));
  const pg = Math.max(1, parseInt(ofKind(q.get("page")), 10) || 1);
  const size = SIZES.includes(+(q.get("size") || 0)) ? +q.get("size")! : 25;
  const all = q.get("states") === "all";

  const set = (changes: Record<string, string | null>, keepPage = false) =>
    setQ((p) => {
      const n = new URLSearchParams(p);
      for (const [k, v] of Object.entries(changes)) { if (v) n.set(k, v); else n.delete(k); }
      if (!keepPage && !("page" in changes)) n.delete("page");   // a new filter or sort: page 1
      return n;
    }, { replace: true });

  const list = useApi<any>("items", {
    kind, n: size, offset: (pg - 1) * size, shown: 1,
    ...(state ? { state } : {}), ...(needle ? { q: needle } : {}), ...(sort ? { sort } : {}), ...(showFin ? { finished: "show" } : {}),
  }, { every: 5000 });
  const fp = useApi<any>(`kinds/${encodeURIComponent(kind)}`, {}, { every: 30000 });
  const flow = useApi<any>("items-flow", { kind, points: 60 }, { every: 30000 });

  const k = list.data?.kinds?.find((x: any) => x.name === kind);
  const [text, setText] = useState(needle);
  useEffect(() => setText(needle), [kind]);   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="page kind-page">
      {k ? (
        <KindBar k={k} level={1} state={state} onState={(st) => set({ state: st })} />
      ) : list.error ? (
        <Page title={kind}><ErrorNote error={list.error} /></Page>
      ) : (
        <h1>{kind}</h1>
      )}

      <section className="kind-sect">
        <h2>Now</h2>
        <span className="seg" role="group" aria-label="States">
          <button type="button" className={!all ? "on" : ""} aria-pressed={!all} onClick={() => set({ states: null }, true)}>State groups</button>
          <button type="button" className={all ? "on" : ""} aria-pressed={all} onClick={() => set({ states: "all" }, true)}>Every state</button>
        </span>
        <NowChart flow={flow.data} fp={fp.data} all={all} />
        <a className="pm-link" href={`/diagram?view=process&kind=${encodeURIComponent(kind)}&mode=states`}
          title="Its process map: how many are in each state now, and how they moved">process map</a>
      </section>

      <section className="kind-sect">
        <h2>In the model</h2>
        <Async state={fp}>{(d) => <InModel fp={d} />}</Async>
      </section>

      <Fold className="kind-sect" summary="Definition">
        {fp.data?.definition ? <Code code={JSON.stringify(fp.data.definition, null, 2)} lang="json" /> : <Loading />}
      </Fold>

      <h2 className="kind-sect">Items</h2>
      <Filters>
        <input type="search" placeholder="Search ids and fields" aria-label="Search" value={text}
          onChange={(ev) => { setText(ev.target.value); set({ q: ev.target.value.trim() || null }); }} />
        {needle && list.data && (
          <span className="muted search-said" aria-live="polite">
            {list.data.total} match{list.data.total === 1 ? "" : "es"}, {list.data.finished ?? 0} finished
          </span>
        )}
        <span className="fin-choice">
          <span className="muted">Finished items:</span>
          <span className="seg fin-seg" role="group" aria-label="Finished items">
            <button type="button" className={!showFin ? "on" : ""} aria-pressed={!showFin} onClick={() => set({ finished: null })}>Hidden</button>
            <button type="button" className={showFin ? "on" : ""} aria-pressed={showFin} onClick={() => set({ finished: "show" })}>Shown</button>
          </span>
        </span>
        {state && (
          <span className="set-chip">
            state {state}{" "}
            <button type="button" className="ghost" title="Remove this filter" aria-label="Remove this filter" onClick={() => set({ state: null })}>×</button>
          </span>
        )}
      </Filters>
      <div className="item-systems">
        <Async state={list}>
          {(d) => {
            const its = d.items.filter((i: any) => i.kind === kind);
            const left = hiddenStates(k).filter((s) => k?.counts?.[s]);
            const nLeft = left.reduce((a, s) => a + k.counts[s], 0);
            const pager = (at: "top" | "foot") => (
              <Pager at={at} d={d} shown={its.length} size={size} pg={pg} what={needle ? "matches" : state || ""}
                onPage={(n) => set({ page: n > 1 ? `${kind}:${n}` : null })}
                onSize={(n) => set({ size: n === 25 ? null : String(n) })} />
            );
            return (
              <section className="sys-group kind-items">
                {its.length ? (
                  <>
                    {pager("top")}
                    <ItemsTable items={its} show={k?.show || []} sort={sort} caption={`${kind} items`}
                      onSort={(s) => set({ sort: s ? `${kind}:${s}` : null })} />
                    {pager("foot")}
                  </>
                ) : (
                  <Empty>{needle ? "Nothing matches." : state ? `No ${kind} items in ${state}.` : "No items to show."}</Empty>
                )}
                {nLeft > 0 && !showFin && !state && !needle && (
                  <p className="note finished-note">
                    {nLeft} finished ({left.join(", ")}) not shown ·{" "}
                    <a href="#" className="finished-flip" onClick={(ev) => { ev.preventDefault(); set({ finished: "show" }); }}>show</a>
                  </p>
                )}
              </section>
            );
          }}
        </Async>
      </div>
    </div>
  );
}

function Pager({ at, d, shown, size, pg, what, onPage, onSize }: {
  at: "top" | "foot"; d: any; shown: number; size: number; pg: number; what: string;
  onPage: (n: number) => void; onSize: (n: number) => void;
}) {
  const reach = d.cut ? Math.min(d.total, d.cut) : d.total;
  const last = Math.max(1, Math.ceil(reach / size));
  return (
    <div className={`pager ${at}`} role="navigation" aria-label={`Pages, ${at}`}>
      <span className="pager-says">
        {d.offset + 1}-{d.offset + shown} of {d.total}{what ? ` ${what}` : ""}
        {d.cut && <span className="muted">, sorted among the newest {d.cut}</span>}
      </span>
      {" · "}<Button variant="ghost" disabled={pg <= 1} onClick={() => onPage(pg - 1)}>Prev</Button>
      {" · "}<Button variant="ghost" disabled={pg >= last} onClick={() => onPage(pg + 1)}>Next</Button>{" "}
      <Select aria-label="Rows a page" value={String(size)} onChange={(ev) => onSize(+ev.target.value)}
        options={SIZES.map((x) => ({ value: String(x), label: `${x} a page` }))} />
    </div>
  );
}

/** Its states over the window, as groups (waiting, working, stopped, done) or each state; and its cycle time. */
function NowChart({ flow, fp, all }: { flow: any; fp: any; all: boolean }) {
  if (!flow) return <Loading />;
  const any = Object.values(flow.counts || {}).some((c: any) => c.some((x: number) => x));
  if (!any) return <p className="muted">Nothing of this kind in the window.</p>;
  let states: string[] = flow.states, counts: Record<string, number[]> = flow.counts;
  if (!all && fp?.group) {
    const grouped: Record<string, number[]> = {};
    for (const [s, c] of Object.entries<number[]>(flow.counts)) {
      const g = fp.group[s] || s;
      grouped[g] = (grouped[g] || flow.times.map(() => 0)).map((x: number, i: number) => x + (c[i] || 0));
    }
    states = (fp.groups || Object.keys(grouped)).filter((g: string) => g in grouped);
    counts = grouped;
  }
  return (
    <div className="kind-flow">
      <FlowChart key={all ? "all" : "groups"} times={flow.times} states={states} counts={counts} height={140} />
      {flow.finished_total > 0 && (
        <p className="muted small">
          {flow.finished_total} finished in the window{flow.median != null ? `, the median took ${dur(flow.median)}` : ""}.
        </p>
      )}
    </div>
  );
}

/** What in the model counts its items, the goals on those parts, the loops they are in, and the states none counts. */
function InModel({ fp }: { fp: any }) {
  if (fp.why) return <p className="muted">{fp.why}</p>;
  const counted = fp.counted_in || [], goals = fp.goals || [], loops = fp.loops || [], taken = fp.taken_by || [];
  if (!counted.length && !goals.length && !taken.length) return <p className="muted">Nothing in the model counts these items.</p>;
  return (
    <div className="kind-model">
      {counted.length > 0 && (
        <p>
          Counted in{" "}
          {counted.map((c: any, i: number) => (
            <span key={c.part}>
              {i ? "; " : ""}
              <a href={`/diagram?view=dynamics&part=${encodeURIComponent(c.part)}`}>{c.kind} {c.name}</a>
              <span className="muted"> ({c.measure ? `${c.measure} of ` : ""}{c.states?.join(", ") || "every state"}{c.system ? `, in ${c.system}` : ""})</span>
            </span>
          ))}
          .
        </p>
      )}
      {taken.length > 0 && (
        <p>Taken by {taken.map((t: any) => (typeof t === "string" ? t : t.block || t.name)).join(", ")}.</p>
      )}
      {goals.length > 0 && (
        <ul className="kind-goals">
          {goals.map((g: any) => (
            <li key={g.goal}>
              <Link to={`/goals?goal=${encodeURIComponent(g.goal)}`}>{g.goal}</Link> holds {g.of} {g.hold}{" "}
              <StatusWord status={g.status} />
              {g.description && <span className="muted"> {g.description}</span>}
            </li>
          ))}
        </ul>
      )}
      {loops.length > 0 && (
        <p className="muted small">
          In {plural(loops.length, "loop")}: {loops.map((l: any) => `${l.name} (${l.polarity})`).join(", ")}.
        </p>
      )}
      {fp.uncounted?.length > 0 && <p className="muted small">Nothing counts it in {fp.uncounted.join(", ")}.</p>}
    </div>
  );
}
