import { Link } from "react-router-dom";
import { plural } from "../lib/format";
import { diagramHref, projectionHref } from "../lib/hrefs";
import { FlowChart } from "./charts/FlowChart";
import { FinishedNote, SystemGroup } from "./controls";
import { hiddenStates, ItemsTable } from "./items";
import { Empty, Note, StatusWord } from "./ui";

/* Projections, the same on every page (kinds.js): the overview's cards under each system (GET /api/items-overview),
   every projection's newest under its system (GET /api/items?per_projection=), and what in the model counts a
   projection (GET /api/projections/P). The Items and Projection pages and any dashboard draw them alike (panels/kinds/items.tsx). */

const perHour = (x: number | null | undefined) =>
  x == null ? "–" : x >= 10 ? String(Math.round(x)) : x >= 1 ? x.toFixed(1) : x ? x.toFixed(2) : "0";

/** A projection's process map: how many are in each state now, and how they moved. */
export function ProcessMapLink({ projection }: { projection: string }) {
  return (
    <a className="pm-link" href={diagramHref({ view: "process", projections: projection })}
      title="Its process map: how many are in each state now, and how they moved">process map</a>
  );
}

/** The overview (an answer of GET /api/items-overview): under each system, a card per projection with its counts, rates and
 *  its states over the window (`all`: each state, else their groups); the projections quiet in the window named after. */
export function ProjectionsOverview({ d, all }: { d: any; all: boolean }) {
  const projectionOf: Record<string, any> = Object.fromEntries(d.projections.map((k: any) => [k.name, k]));
  const quiet = d.projections.filter((k: any) => k.quiet);
  return (
    <div className="projection-overview">
      {d.systems.map((g: any) => {
        const ks = g.projections.map((n: string) => projectionOf[n]).filter((k: any) => k && !k.quiet);
        if (!ks.length) return null;
        const n = ks.reduce((a: number, k: any) => a + (k.total || 0), 0);
        return (
          <SystemGroup key={g.name} name={g.name} count={`${plural(n, "item")}, ${plural(ks.length, "projection")}`} description={g.description}>
            <div className="projection-cards">
              {ks.map((k: any) => <ProjectionCard key={k.name} k={k} d={d} all={all} />)}
            </div>
          </SystemGroup>
        );
      })}
      {quiet.length > 0 && (
        <p className="muted projections-quiet">
          Nothing in the window:{" "}
          {quiet.map((k: any, i: number) => (
            <span key={k.name}>{i ? ", " : ""}<Link to={projectionHref(k.name)}>{k.title || k.name}</Link></span>
          ))}
        </p>
      )}
      {d.unprojected > 0 && <Note>{plural(d.unprojected, "item")} match no projection of the model's.</Note>}
      {!d.projections.length && <Empty>No items yet. An item is what events with an id like ticket/12 are about (ergostat help spec).</Empty>}
    </div>
  );
}

function ProjectionCard({ k, d, all }: { k: any; d: any; all: boolean }) {
  const states: string[] = all ? k.states : d.groups.filter((g: string) => k.by_group && g in k.by_group);
  return (
    <div className="projection-flow projection-card" data-projection={k.name}>
      <Link to={projectionHref(k.name)} className="kname">
        {k.title || k.name}
        <span className="mono">{k.title ? k.name : k.id}</span>
      </Link>
      <ProcessMapLink projection={k.name} />
      {k.why ? (
        <div className="projection-counts muted small">{k.why}</div>
      ) : (
        <div className="projection-counts small">
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

/** Every projection's items (an answer of GET /api/items?per_projection=N): under each system, each projection's newest, matched to the
 *  search `needle`; `showFin`: its finished shown too. */
export function EveryProjection({ d, needle, showFin }: { d: any; needle: string; showFin: boolean }) {
  const projectionOf: Record<string, any> = Object.fromEntries(d.projections.map((k: any) => [k.name, k]));
  const hits: Record<string, number> | null = needle ? d.matched || {} : null;
  const hitsN = hits ? Object.values(hits).reduce((a, b) => a + b, 0) : 0;
  const systems = d.systems || [{ name: "", projections: d.projections.map((k: any) => k.name) }];
  return (
    <div className="item-systems">
      {needle && <p className="muted search-hits" aria-live="polite">{hitsN ? `${hitsN} match${hitsN === 1 ? "" : "es"}` : "nothing matches"}</p>}
      {d.unprojected > 0 && <Note>{plural(d.unprojected, "item")} match no projection of the model's; shown with their fields, no state.</Note>}
      {!d.projections.length && !d.unprojected && <Empty>No items yet. An item is what events with an id like ticket/12 are about (ergostat help spec).</Empty>}
      {systems.map((g: any) => {
        const names: string[] = [...g.projections, ...(g.name === "other" && d.unprojected ? [""] : [])];
        if (hits && !names.some((n) => hits[n] > 0)) return null;
        const parts = names.map((name) => {
          const its = d.items.filter((i: any) => (i.projection || "") === name);
          const k = projectionOf[name];
          const left = hiddenStates(k).filter((s) => k?.counts?.[s]);
          const nLeft = left.reduce((a, s) => a + k.counts[s], 0);
          if (!its.length && !(nLeft && !showFin && !needle)) return null;
          return (
            <div key={name || "-"}>
              <h3 className="projection-head">
                {k ? <Link to={projectionHref(name)}>{k.title || name}</Link> : "No projection"}
                {k?.title && <span className="muted small mono"> {name}</span>}
                <span className="muted"> {d.matched?.[name] ?? its.length}</span>
              </h3>
              {its.length > 0 && <ItemsTable items={its} show={k?.show || []} caption={`${name || "No projection"} items`} />}
              {!showFin && !needle && <FinishedNote n={nLeft} states={left} />}
            </div>
          );
        }).filter(Boolean);
        if (!parts.length) return null;
        return <SystemGroup key={g.name} name={g.name} count={plural(g.projections.length, "projection")} description={g.description}>{parts}</SystemGroup>;
      })}
    </div>
  );
}

/** What in the model counts a projection's items (an answer of GET /api/projections/P), the goals on those parts, the loops
 *  they are in, and the states none counts. */
export function ProjectionModel({ fp }: { fp: any }) {
  if (fp.why) return <p className="muted">{fp.why}</p>;
  const counted = fp.counted_in || [], goals = fp.goals || [], loops = fp.loops || [], taken = fp.taken_by || [];
  if (!counted.length && !goals.length && !taken.length) return <p className="muted">Nothing in the model counts these items.</p>;
  return (
    <div className="projection-model">
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
        <ul className="projection-goals">
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
