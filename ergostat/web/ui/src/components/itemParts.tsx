import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ago, dur, nowS, stamp } from "../lib/format";
import { diagramHref, itemHref, projectionHref } from "../lib/hrefs";
import { Meta } from "./controls";
import { EventsTable, useShowEvent } from "./events";
import { FieldValue, isShort } from "./items";
import { Table } from "./Table";
import { Empty, Loading, Note } from "./ui";

/* An item's parts (pages.js pageItem), each drawn from its answer (GET /api/items/ID, `d`): its projection, state and age;
   why it is not done (GET /api/why); the path it took through its states; its relations both ways; its fields (its
   projection's chosen first, a long one as Markdown); what was refused; how it moved; its events; each field's changes.
   The Item page and any dashboard draw them alike (panels/kinds/items.tsx). */

/** An event of the item's record by its id, as a link that opens it; its type alone when it is not on the record. */
export function useEventLink(d: any): (eid: string, type: string) => ReactNode {
  const showEvent = useShowEvent();
  return (eid, type) => {
    const e = (d.record || []).find((x: any) => x.id === eid);
    return e ? <a href="#" className="plain" title={`event ${eid}`} onClick={(ev) => { ev.preventDefault(); showEvent(e); }}>{type}</a> : <span>{type}</span>;
  };
}

/** Its projection, state, when it is expected done, how many events, its first and latest. */
export function ItemSummary({ d }: { d: any }) {
  const k = d.projection_of;
  return (
    <Meta rows={[
      ["Projection", k ? <Link to={projectionHref(k.name)}>{k.name}</Link> : <span className="muted">none (no projection matches this id)</span>],
      ["State", d.state && <span><b>{d.state}</b> for {dur(nowS() - d.entered)}</span>],
      ["Expected done", d.eta?.unscheduled ? <span data-eta="">not scheduled: {d.eta.said || "it cannot move"}</span>
        : d.eta?.p50 && <span data-eta=""><b>{stamp(d.eta.p50)}</b>{d.eta.p90 ? <span className="muted"> (90% by {stamp(d.eta.p90)})</span> : null}</span>],
      ["Events", String(d.events)],
      ["First", ago(d.first)],
      ["Latest", <span>{d.latest}<span className="muted">, {ago(d.last)}</span></span>],
    ]} />
  );
}

/** Whether there is anything to say of why it is not done (GET /api/why's answer). */
export const whySays = (why: any) => !!(why && why.known && !why.done);

/** Why it is not done: the summary, the command that would move it, the evidence. */
export function ItemWhy({ why }: { why: any }) {
  return (
    <div className="note why" data-why={why.root ? why.root.kind : "unknown"}>
      {why.summary}
      {why.root?.command && <p><span className="muted">{why.root.owner}: </span><code>{why.root.command}</code></p>}
      {why.evidence?.length > 0 && (
        <ul className="small">
          {why.evidence.slice(0, 6).map((e: any) => <li key={`${e.says}|${e.link}`}>{e.link ? <a href={e.link}>{e.says}</a> : e.says}</li>)}
        </ul>
      )}
    </div>
  );
}

/** Whether its projection has states to draw a path through. */
export const hasPath = (d: any) => !!d.projection_of?.states?.length;

/** Where it went: the path it took, arrow by arrow, to where it is now; the other states apart (its endings
 *  double-bordered); where the model draws its path; and why its estimate waits. */
export function ItemPath({ d }: { d: any }) {
  const k = d.projection_of;
  const fin = new Set<string>(k?.final || []);
  const path: string[] = d.moves.map((m: any) => m.to).filter((s: string, i: number, a: string[]) => s && s !== a[i - 1]);
  if (d.state && path[path.length - 1] !== d.state) path.push(d.state);
  const ended = fin.has(d.state);
  const rest: string[] = (k?.states || []).filter((s: string) => !path.includes(s) && (!ended || fin.has(s)));
  const box = (st: string) => <span key={st} className={`stbox${st === d.state ? " on" : ""}${fin.has(st) ? " final" : ""}`}>{st}</span>;
  const counted = !!d.path?.some((st: any) => st.stock || st.flow || st.block);
  return (
    <>
      {hasPath(d) ? (
        <>
          <div className="track">
            {path.map((st, i) => <span key={st + i}>{i > 0 && <span className="arrow" aria-hidden="true">→</span>}{box(st)}</span>)}
            {rest.length > 0 && <span className="alt">{ended ? "could also have ended:" : "its other states:"}{rest.map(box)}</span>}
          </div>
          {d.path && (counted ? (
            <p className="went">
              <a href={diagramHref({ item: d.id })}>Draw its path in Dynamics</a>, <a href={diagramHref({ view: "blocks", item: d.id })}>in Blocks</a>
              {k && <>; <a href={diagramHref({ projection: k.name })}>what every {k.name} touches</a></>}.
            </p>
          ) : <p className="went muted uncounted">Its moves are not counted anywhere in the model.</p>)}
          {d.path?.some((p: any) => p.says) && (
            <ul className="small muted">{d.path.filter((p: any) => p.says).map((p: any) => <li key={p.state}>{p.says}</li>)}</ul>
          )}
        </>
      ) : <p className="muted">Its projection has no states.</p>}
      {d.eta?.why && <p className="note eta-why">{d.eta.waits_in && <b>Waiting in {d.eta.waits_in}: </b>}{d.eta.why}</p>}
    </>
  );
}

const relationRows = (r: any): [string, string[], any][] => !r ? [] : [
  ...Object.entries<string[]>(r.out || {}).map(([n, ids]) => [n, ids, r.relations?.[n]] as [string, string[], any]),
  ...Object.entries<string[]>(r.in || {}).map(([n, ids]) => [n, ids, null] as [string, string[], any]),
];

/** Whether it names, or is named by, anything. */
export const hasRelations = (d: any) => relationRows(d.relations).length > 0;

/** Its relations both ways (pages.js relationsView): what it names, and what names it, each related item's state. */
export function ItemRelations({ d }: { d: any }) {
  const r = d.relations, k = d.projection_of;
  const rows = relationRows(r);
  if (!rows.length) return <p className="muted">It names no other item, and none names it.</p>;
  return (
    <>
      {r.waiting?.length ? <Note><b>Waiting on </b>{r.waiting.join(", ")}: not finished yet.</Note>
        : r.relations && Object.values<any>(r.relations).some((x) => x.precedence) ? <Note>Nothing it waits on is unfinished.</Note> : null}
      <Table caption="Relations" className="fields relations">
        <Table.Body>
          {rows.map(([n, ids, rel]) => (
            <tr key={n}>
              <th scope="row">
                {n.replace(/_/g, " ")}
                <span className="muted small rule">{rel ? (rel.precedence ? " precedence" : rel.group ? " parent" : "") : " derived"}</span>
              </th>
              <td>
                {ids.map((i, j) => {
                  const x = r.items?.[i];
                  return (
                    <span key={i} className="rel-item">
                      {j > 0 && <br />}
                      <Link to={itemHref(i)}>{i}</Link>
                      <span className="muted">{x ? ` ${x.done ? "✓ " : ""}${x.state || ""}${x.title ? " · " + x.title : ""}` : " not recorded"}</span>
                    </span>
                  );
                })}
              </td>
            </tr>
          ))}
        </Table.Body>
      </Table>
      {k && <Note>All of them in <a href={`${projectionHref(k.name, "view=graph")}`}>the graph</a>.</Note>}
    </>
  );
}

/** Its fields: its projection's chosen first, in their order, then the rest by name; a removed one that has changes still
 *  listed. `onChanges`: a field's "N changes" opens its changes (where the page has them). */
export function ItemFields({ d, onChanges }: { d: any; onChanges?: (field: string) => void }) {
  const k = d.projection_of;
  const counts: Record<string, number> = d.changes || {};
  const first: string[] = (k?.show || []).filter((f: string) => f in d.fields);
  const gone = Object.keys(counts).filter((f) => f && !(f in d.fields));
  const order = [...first, ...Object.keys(d.fields).filter((f) => !first.includes(f)).sort(), ...gone.sort()].filter((f) => f !== "lease");
  const grid = order.filter((f) => !(f in d.fields) || isShort(d.fields[f]));
  const fname = (f: string) => (
    <>
      {f}
      {k?.fold?.[f] && <span className="muted small rule" title="how its events' data folds into it"> {k.fold[f]}</span>}
      {counts[f] > 1 && (onChanges ? (
        <a className="small changes-of" href="#changes" onClick={(ev) => { ev.preventDefault(); onChanges(f); document.getElementById("changes")?.scrollIntoView(); }}>
          {" "}{counts[f]} changes
        </a>
      ) : <span className="small muted changes-of"> {counts[f]} changes</span>)}
    </>
  );
  if (!order.length) return <p className="muted">No fields: its events carry no data.</p>;
  return (
    <>
      {grid.length > 0 && (
        <div className="field-grid">
          {grid.map((f) => (
            <div className="field" data-field={f} key={f}>
              <div className="field-name">{fname(f)}</div>
              <div>{f in d.fields ? <FieldValue name={f} value={d.fields[f]} /> : <span className="muted">removed</span>}</div>
            </div>
          ))}
        </div>
      )}
      {order.filter((f) => !grid.includes(f)).map((f) => (
        <div className="field-block" data-field={f} key={f}>
          <h3>{fname(f)}</h3>
          <FieldValue name={f} value={d.fields[f]} />
        </div>
      ))}
    </>
  );
}

/** Events recorded that changed nothing: their changeset could not apply, so none of it did. */
export function ItemRefused({ d }: { d: any }) {
  const eventLink = useEventLink(d);
  if (!d.refused?.length) return <p className="muted">Nothing refused: every event's change applied.</p>;
  return (
    <>
      <Note>Events recorded that changed nothing: their changeset could not apply, so none of it did.</Note>
      <div className="panel-table">
        <Table caption="Refused events">
          <Table.Head><Table.Th>when</Table.Th><Table.Th>event</Table.Th><Table.Th>as</Table.Th><Table.Th>why</Table.Th></Table.Head>
          <Table.Body>
            {d.refused.slice().reverse().map((r: any) => (
              <tr key={r.event}>
                <td className="nowrap">{stamp(r.time)}</td><td className="nowrap">{eventLink(r.event, r.type)}</td>
                <td className="muted">{r.form}</td><td>{r.why}</td>
              </tr>
            ))}
          </Table.Body>
        </Table>
      </div>
    </>
  );
}

/** How it moved: each move's time, from, to, the event that moved it and how long after the one before. */
export function ItemMoves({ d }: { d: any }) {
  const eventLink = useEventLink(d);
  if (!d.moves.length) return <p className="muted">Its projection has no states.</p>;
  return (
    <div className="panel-table">
      <Table caption="Its moves">
        <Table.Head><Table.Th>when</Table.Th><Table.Th>from</Table.Th><Table.Th>to</Table.Th><Table.Th>by event</Table.Th><Table.Th num>after</Table.Th></Table.Head>
        <Table.Body>
          {d.moves.map((m: any, i: number) => (
            <tr key={`${m.time}|${m.to}`}>
              <td className="nowrap">{stamp(m.time)}</td>
              <td className={m.from ? "" : "muted"}>{m.from || "arrived"}</td>
              <td>{m.to}</td>
              <td className="muted">{eventLink(m.event, m.type)}</td>
              <td className="num muted">{i ? dur(m.time - d.moves[i - 1].time) : ""}</td>
            </tr>
          ))}
        </Table.Body>
      </Table>
    </div>
  );
}

/** Its events, newest first, with what is not listed (its transcript's lines, a rolled-up past). */
export function ItemEvents({ d }: { d: any }) {
  return (
    <>
      {d.transcript_events > 0 && (
        <Note>
          {d.transcript_events} more events are its transcript's lines (claude.*), folded into its fields;{" "}
          <Link to={`/record?item=${encodeURIComponent(d.id)}`}>all of them in the Record</Link>.
        </Note>
      )}
      {d.rollup && (
        <Note>Its {d.rollup.archived?.events} oldest events, up to {stamp(d.rollup.last)}, are rolled up into one snapshot and archived.</Note>
      )}
      {d.record?.length ? <EventsTable events={d.record} compact /> : <Empty>No events.</Empty>}
    </>
  );
}

export const CHANGES_SHOWN = 200;

/** Each field's changes, the latest first (pages.js historyView): `of` one field's, or every field's (""). `all`: the
 *  way back to every field's, where one field's is shown. */
export function ItemChanges({ d, of, all }: { d: any; of: string; all?: () => void }) {
  const eventLink = useEventLink(d);
  if (!d.history) return <Loading />;
  const fs = Object.keys(d.history).filter((f) => !of || f === of);
  const rows = fs.flatMap((f) => d.history[f].slice(-CHANGES_SHOWN).slice().reverse().map((c: any) => ({ f, c })));
  const total = fs.reduce((n, f) => n + (d.changes?.[f] || 0), 0);
  const how = (c: any) =>
    c.op === "rolled up" ? `${c.count} change${c.count > 1 ? "s" : ""} from ${stamp(c.first?.time)}, rolled up`
      : c.op === "refused" ? "refused" : c.op + (c.rule && c.rule !== "replace" ? ` (${c.rule})` : "") + (c.form !== "data" ? ` by ${c.form}` : "");
  return (
    <>
      <Note>
        {of ? <>The changes to {of}{all && <>; <a href="#changes" onClick={(ev) => { ev.preventDefault(); all(); }}>every field's</a></>}.</> : "Each field's changes, the latest first."}
        {rows.length < total && <> The latest {CHANGES_SHOWN} of a field's; <code>ergostat item {d.id} --history</code> lists all.</>}
      </Note>
      {rows.length ? (
        <div className="panel-table">
          <Table caption="Changes" className="history">
            <Table.Head>
              <Table.Th>when</Table.Th><Table.Th>change</Table.Th><Table.Th>path</Table.Th><Table.Th>before</Table.Th><Table.Th>after</Table.Th><Table.Th>by event</Table.Th>
            </Table.Head>
            <Table.Body>
              {rows.map(({ f, c }: any, i: number) => (
                <tr key={`${c.event}|${c.path}|${c.op}|${i}`}>
                  <td className="nowrap">{stamp(c.time)}</td>
                  <td className="nowrap">{how(c)}</td>
                  <td className="mono small">{c.path || "/"}</td>
                  <td className="cell">{c.op === "refused" ? c.why : <FieldValue name={f} value={c.before} cell />}</td>
                  <td className="cell">{c.op === "refused" ? "" : <FieldValue name={f} value={c.after} cell />}</td>
                  <td className="nowrap">{c.event ? eventLink(c.event, c.type) : ""}</td>
                </tr>
              ))}
            </Table.Body>
          </Table>
        </div>
      ) : <p className="muted">No changes.</p>}
    </>
  );
}
