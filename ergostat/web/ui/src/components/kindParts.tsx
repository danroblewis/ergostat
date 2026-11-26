import { Link } from "react-router-dom";
import { plural } from "../lib/format";
import { diagramHref, kindHref } from "../lib/hrefs";
import { FlowChart } from "./charts/FlowChart";
import { FinishedNote, SystemGroup } from "./controls";
import { hiddenStates, ItemsTable } from "./items";
import { Empty, Note, StatusWord } from "./ui";

/* Kinds of item, the same on every page (kinds.js): the overview's cards under each system (GET /api/items-overview),
   every kind's newest under its system (GET /api/items?per_kind=), and what in the model counts a kind (GET
   /api/kinds/KIND). The Items and Kind pages and any dashboard draw them alike (panels/kinds/items.tsx). */

const perHour = (x: number | null | undefined) =>
  x == null ? "–" : x >= 10 ? String(Math.round(x)) : x >= 1 ? x.toFixed(1) : x ? x.toFixed(2) : "0";

/** A kind's process map: how many are in each state now, and how they moved. */
export function ProcessMapLink({ kind }: { kind: string }) {
  return (
    <a className="pm-link" href={diagramHref({ view: "process", kinds: kind })}
      title="Its process map: how many are in each state now, and how they moved">process map</a>
  );
}

/** The overview (an answer of GET /api/items-overview): under each system, a card per kind with its counts, rates and
 *  its states over the window (`all`: each state, else their groups); the kinds quiet in the window named after. */
export function KindsOverview({ d, all }: { d: any; all: boolean }) {
  const kindOf: Record<string, any> = Object.fromEntries(d.kinds.map((k: any) => [k.name, k]));
  const quiet = d.kinds.filter((k: any) => k.quiet);
  return (
    <div className="kind-overview">
      {d.systems.map((g: any) => {
        const ks = g.kinds.map((n: string) => kindOf[n]).filter((k: any) => k && !k.quiet);
        if (!ks.length) return null;
        const n = ks.reduce((a: number, k: any) => a + (k.total || 0), 0);
        return (
          <SystemGroup key={g.name} name={g.name} count={`${plural(n, "item")}, ${plural(ks.length, "kind")}`} description={g.description}>
            <div className="kind-cards">
              {ks.map((k: any) => <KindCard key={k.name} k={k} d={d} all={all} />)}
            </div>
          </SystemGroup>
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
    </div>
  );
}

function KindCard({ k, d, all }: { k: any; d: any; all: boolean }) {
  const states: string[] = all ? k.states : d.groups.filter((g: string) => k.by_group && g in k.by_group);
  return (
    <div className="kind-flow kind-card" data-kind={k.name}>
      <Link to={kindHref(k.name)} className="kname">
        {k.title || k.name}
        <span className="mono">{k.title ? k.name : k.id}</span>
      </Link>
      <ProcessMapLink kind={k.name} />
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

/** Every kind's items (an answer of GET /api/items?per_kind=N): under each system, each kind's newest, matched to the
 *  search `needle`; `showFin`: its finished shown too. */
export function EveryKind({ d, needle, showFin }: { d: any; needle: string; showFin: boolean }) {
  const kindOf: Record<string, any> = Object.fromEntries(d.kinds.map((k: any) => [k.name, k]));
  const hits: Record<string, number> | null = needle ? d.matched || {} : null;
  const hitsN = hits ? Object.values(hits).reduce((a, b) => a + b, 0) : 0;
  const systems = d.systems || [{ name: "", kinds: d.kinds.map((k: any) => k.name) }];
  return (
    <div className="item-systems">
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
              {!showFin && !needle && <FinishedNote n={nLeft} states={left} />}
            </div>
          );
        }).filter(Boolean);
        if (!parts.length) return null;
        return <SystemGroup key={g.name} name={g.name} count={plural(g.kinds.length, "kind")} description={g.description}>{parts}</SystemGroup>;
      })}
    </div>
  );
}

/** What in the model counts a kind's items (an answer of GET /api/kinds/KIND), the goals on those parts, the loops
 *  they are in, and the states none counts. */
export function KindModel({ fp }: { fp: any }) {
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
              <a href={diagramHref({ around: `${c.kind}/${c.name}` })}>{c.kind} {c.name}</a>
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
              <Link to={`/goals?select=${encodeURIComponent(g.goal)}`}>{g.goal}</Link> holds {g.of} {g.hold}{" "}
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
