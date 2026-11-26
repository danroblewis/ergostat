import { Link, useParams, useSearchParams } from "react-router-dom";
import { Async, Code, Empty, ErrorNote, Filters, FinishedNote, FinishedToggle, Fold, ItemsTable, KindBar, KindStates, Loading, Page, PAGE_SIZES, Pager, SearchBox, StatesChoice, StatusWord, hiddenStates } from "../../components";
import { useApi } from "../../hooks/useApi";
import { plural } from "../../lib/format";

/* /items/KIND (pages.js pageItems with ``only``, kindpage.js): its bar as the page's heading (a state chip filters
   the list), Now (its states over the window and how long its finished took), In the model (what counts it, the
   goals and loops it is in), its definition, then its items, a page at a time, searched and sorted by the server.
   Every choice is in the address: state=, q=, finished=show, sort=KIND:field, page=KIND:N, size=, states=all. */

const SIZES = PAGE_SIZES;

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
        <StatesChoice all={all} onChange={(v) => set({ states: v ? "all" : null }, true)} />
        <KindStates flow={flow.data} fp={fp.data} all={all} />
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
        <SearchBox value={needle} live placeholder="Search ids and fields" onSearch={(w) => set({ q: w || null })} />
        {needle && list.data && (
          <span className="muted search-said" aria-live="polite">
            {list.data.total} match{list.data.total === 1 ? "" : "es"}, {list.data.finished ?? 0} finished
          </span>
        )}
        <FinishedToggle shown={showFin} onChange={(v) => set({ finished: v ? "show" : null })} />
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
              <Pager at={at} total={d.total} offset={d.offset} cut={d.cut} shown={its.length} size={size} what={needle ? "matches" : state || ""}
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
                {!showFin && !state && !needle && <FinishedNote n={nLeft} states={left} onShow={() => set({ finished: "show" })} />}
              </section>
            );
          }}
        </Async>
      </div>
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
