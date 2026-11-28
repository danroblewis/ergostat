import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ago, dur, nowS, stamp } from "../lib/format";
import { diagramHref, eventsHref, itemHref, projectionHref } from "../lib/hrefs";
import { projectionsOfId } from "../lib/routes";
import { eventName } from "./charts/ItemCharts";
import { Meta, Pager } from "./controls";
import { useShowEvent } from "./events";
import { FieldValue, isShort } from "./items";
import { Table } from "./Table";
import { Empty, Loading, Note } from "./ui";

/* An item's parts (pages.js pageItem), each drawn from its answer (GET /api/items/ID, `d`): its projection, state and age
   (with what it belongs to, and its path on the diagrams); why it is not done (GET /api/why); its relations both ways;
   its fields (its projection's chosen first; nested maps as rows, a built-in's bookkeeping folded); what was refused;
   and its history: each event, newest first, with what it changed. The Item page and any dashboard draw them alike
   (panels/kinds/items.tsx). */

/** An event of the item's record by its id, as a link that opens it; its type alone when it is not on the record. */
export function useEventLink(d: any): (eid: string, type: string) => ReactNode {
  const showEvent = useShowEvent();
  return (eid, type) => {
    const e = (d.record || []).find((x: any) => x.id === eid);
    return e ? <a href="#" className="plain" title={`event ${eid}`} onClick={(ev) => { ev.preventDefault(); showEvent(e); }}>{type}</a> : <span>{type}</span>;
  };
}

/** Whether its projection is one of ergostat's own (ergostat.*): its items are ergostat's bookkeeping. */
export const builtIn = (d: any) => String(d?.projection || d?.projection_of?.name || "").startsWith("ergostat.");

/** The owner-facing object a built-in bookkeeping item belongs to: a modelling request raised for a group of
 *  unexplained events is that group's (ergostat.unexplained/ID, the one thing the owner watches). Null: none. */
export function belongsTo(d: any): { id: string; projection: string; says: string } | null {
  const f = d?.fields || {};
  if (d?.projection === "ergostat.modelling-request" && f.source === "events" && typeof f.about === "string" && f.about.startsWith("events:")) {
    const g = f.group || {};
    const label = `${g.type || "(no type)"}${g.source ? ` from ${g.source}` : ""}${g.shape ? ` shaped {${g.shape}}` : ""}`;
    return { id: `ergostat.unexplained/${f.about.slice("events:".length)}`, projection: "ergostat.unexplained", says: `This is the group ${label}` };
  }
  return null;
}

/** Its projection, state, when it is expected done (and why it waits), how many events, its first and latest; first,
 *  what it belongs to (a built-in's owner-facing object); last, its path drawn on the diagrams. */
export function ItemSummary({ d }: { d: any }) {
  const k = d.projection_of;
  const of = belongsTo(d);
  const counted = !!d.path?.some((st: any) => st.stock || st.flow || st.block);
  return (
    <>
      {of && <p className="item-belongs" data-testid="belongs-to">{of.says}:{" "}
        <Link to={itemHref(of.id, undefined, of.projection)}>{of.id}</Link></p>}
      <Meta rows={[
        ["Projection", k ? <Link to={projectionHref(k.name)}>{k.name}</Link> : <span className="muted">none (no projection matches this id)</span>],
        ["State", d.state && <span><b>{d.state}</b> for {dur(nowS() - d.entered)}</span>],
        ["Expected done", d.eta?.unscheduled ? <span data-eta="">not scheduled: {d.eta.said || "it cannot move"}</span>
          : d.eta?.p50 && <span data-eta=""><b>{stamp(d.eta.p50)}</b>{d.eta.p90 ? <span className="muted"> (90% by {stamp(d.eta.p90)})</span> : null}
            {d.eta.why && <span className="muted eta-why">; {d.eta.waits_in ? `waiting in ${d.eta.waits_in}: ` : ""}{d.eta.why}</span>}</span>],
        ["Events", String(d.events)],
        ["First", ago(d.first)],
        ["Latest", <span>{d.latest}<span className="muted">, {ago(d.last)}</span></span>],
        ["On the diagrams", counted && <span className="went">
          <a href={diagramHref({ item: d.id })}>its path in System dynamics</a>, <a href={diagramHref({ view: "blocks", item: d.id })}>in Blocks</a>
        </span>],
      ]} />
    </>
  );
}

/** Whether there is anything worth saying of why it is not done (GET /api/why's answer): an unfinished item of the
 *  model's own projections, with a cause known and someone to act on it. Never for ergostat's built-in projections. */
export const whySays = (why: any) => !!(why && why.known && !why.done && why.root && why.root.kind !== "unknown"
  && !String(why.kind || why.item || "").startsWith("ergostat."));

/** A link of the answer that is not the item's own page (a link back to the page it is on says nothing). */
const elsewhere = (link: string | null | undefined, item: string) => {
  if (!link) return false;
  let at = link;
  try { at = decodeURIComponent(link); } catch { /* as it is */ }
  return !at.split("?")[0].endsWith(`/${item}`);
};

/** Why it is not done, in one line: what holds it and who is to act (and the command); the whole answer (`ergostat
 *  why`'s paragraph and its evidence) behind a "why" disclosure. */
export function ItemWhy({ why }: { why: any }) {
  const r = why.root || {};
  const evidence: any[] = why.evidence || [];
  return (
    <div className="note why" data-why={r.kind || "unknown"}>
      <p className="why-line">Waiting: {r.says}. Next: {r.owner} to {r.action}{r.command && <>{" "}<code>{r.command}</code></>}.</p>
      <details className="why-more">
        <summary>why</summary>
        <p className="small">{why.summary}</p>
        {evidence.length > 0 && (
          <ul className="small">
            {evidence.slice(0, 6).map((e: any) => <li key={`${e.says}|${e.link}`}>{e.link && elsewhere(e.link, why.item) ? <a href={e.link}>{e.says}</a> : e.says}</li>)}
          </ul>
        )}
      </details>
    </div>
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
                      <Link to={itemHref(i, undefined, x?.projection)} title={x?.name ? i : undefined}>{x?.name || i}</Link>
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


/** A string that names an item of one of the model's projections (not the item `self`): its id. */
const itemNamed = (v: unknown, self?: string) =>
  typeof v === "string" && v !== self && /^[^\s/]+\/\S+$/.test(v) && projectionsOfId(v).length > 0 ? v : null;

/** A field's value as readable as it can be: a map as nested key/value rows, a list as a list, a time as a time, a long
 *  text as text, an id of an item as a link to its page (never to `self`, the page it is on). */
export function NestedValue({ name, value, self, depth = 0 }: { name: string; value: unknown; self?: string; depth?: number }): ReactNode {
  const id = itemNamed(value, self);
  if (id) return <Link to={itemHref(id)}>{id}</Link>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="muted">none</span>;
    if (depth > 4) return <span className="mono small">{JSON.stringify(value)}</span>;
    return (
      <ul className="field-list">
        {value.map((v, i) => <li key={i}><NestedValue name={name} value={v} self={self} depth={depth + 1} /></li>)}
      </ul>
    );
  }
  if (value && typeof value === "object") {
    const es = Object.entries(value as Record<string, unknown>);
    if (!es.length) return <span className="muted">none</span>;
    if (depth > 4) return <span className="mono small">{JSON.stringify(value)}</span>;
    return (
      <dl className="field-map">
        {es.map(([k, v]) => (
          <div key={k} className="field-map-row" data-key={k}><dt>{k.replace(/_/g, " ")}</dt>
            <dd><NestedValue name={k} value={v} self={self} depth={depth + 1} /></dd></div>
        ))}
      </dl>
    );
  }
  return <FieldValue name={name} value={value} />;
}

/** Its fields: its projection's chosen first, in their order, then the rest by name. A built-in's (ergostat.*) fields
 *  its projection does not choose are ergostat's bookkeeping, folded apart. */
export function ItemFields({ d }: { d: any }) {
  const k = d.projection_of;
  const fields: Record<string, unknown> = d.fields || {};
  const first: string[] = (k?.show || []).filter((f: string) => f in fields);
  const order = [...first, ...Object.keys(fields).filter((f) => !first.includes(f)).sort()].filter((f) => f !== "lease");
  const own = builtIn(d) ? order.filter((f) => first.includes(f)) : order;
  const kept = builtIn(d) ? order.filter((f) => !first.includes(f)) : [];
  const fname = (f: string) => (
    <>
      {f.replace(/_/g, " ")}
      {!builtIn(d) && (k?.events?.["*"]?.[f] || k?.fold?.[f]) && <span className="muted small rule" title="how every event it reads folds into it">
        {" "}{k?.events?.["*"]?.[f] || k.fold[f]}</span>}
    </>
  );
  const list = (fs: string[]) => {
    const grid = fs.filter((f) => isShort(fields[f]) && !itemNamed(fields[f], d.id));
    return (
      <>
        {grid.length > 0 && (
          <div className="field-grid">
            {grid.map((f) => (
              <div className="field" data-field={f} key={f}>
                <div className="field-name">{fname(f)}</div>
                <div><FieldValue name={f} value={fields[f]} /></div>
              </div>
            ))}
          </div>
        )}
        {fs.filter((f) => !grid.includes(f)).map((f) => (
          <div className="field-block" data-field={f} key={f}>
            <h3>{fname(f)}</h3>
            <NestedValue name={f} value={fields[f]} self={d.id} />
          </div>
        ))}
      </>
    );
  };
  if (!order.length) return <p className="muted">No fields: its events carry no data.</p>;
  return (
    <>
      {own.length ? list(own) : kept.length ? null : <p className="muted">No fields.</p>}
      {kept.length > 0 && (
        <details className="bookkeeping" data-testid="bookkeeping">
          <summary>ergostat's bookkeeping ({kept.length} field{kept.length > 1 ? "s" : ""})</summary>
          {list(kept)}
        </details>
      )}
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

// ---- its history: each event, newest first, with what it changed

export interface Change { field: string; path: string; op: string; before: unknown; after: unknown }
export interface Entry { e: any; evs: any[]; move?: any; changes: Change[]; refused?: string }

/** Its history (its record, newest first): each event with the move it made and each field change it made (from its
 *  answer's `moves`, `history` and `refused`); a run of events in a row of one kind that changed nothing, one entry. */
export function historyOf(d: any): Entry[] {
  const changes: Record<string, Change[]> = {};
  for (const [f, cs] of Object.entries<any[]>(d.history || {})) {
    for (const c of cs) {
      if (!c.event || c.op === "rolled up" || c.op === "refused") continue;
      (changes[c.event] ??= []).push({ field: f, path: c.path || `/${f}`, op: c.op, before: c.before, after: c.after });
    }
  }
  const moves: Record<string, any> = {};
  for (const m of d.moves || []) if (m.event) moves[m.event] = m;
  const refused: Record<string, string> = {};
  for (const r of d.refused || []) if (r.event) refused[r.event] = r.why || "refused";
  const out: Entry[] = [];
  for (const e of (d.record || []).slice().reverse()) {
    const move = moves[e.id];
    const cs = (changes[e.id] || []).filter((c) => !(move && c.path === "/state"));
    const entry: Entry = { e, evs: [e], move, changes: cs, refused: refused[e.id] };
    const last = out[out.length - 1];
    const nothing = (x: Entry) => !x.move && !x.changes.length && !x.refused;
    if (last && nothing(last) && nothing(entry) && last.e.type === e.type && (last.e.kind || "") === (e.kind || "")
      && (last.e.source || "") === (e.source || "")) last.evs.push(e);
    else out.push(entry);
  }
  return out;
}

/** A value in a change, shortly: a map or a list said by its size, the rest as a field's value is in a cell. */
function Brief({ name, v }: { name: string; v: unknown }) {
  if (Array.isArray(v)) return <span className="muted">{v.length ? `a list of ${v.length}` : "an empty list"}</span>;
  if (v && typeof v === "object") {
    const ks = Object.keys(v);
    return <span className="muted" title={ks.join(", ")}>{ks.length ? `${ks.slice(0, 3).join(", ")}${ks.length > 3 ? ", …" : ""}` : "an empty map"}</span>;
  }
  return <FieldValue name={name} value={v} cell />;
}

function ChangeLine({ c }: { c: Change }) {
  const where = c.path.replace(/^\//, "").split("/").map((s) => s.replace(/~1/g, "/").replace(/~0/g, "~")).join(" · ") || c.field;
  const was = c.before !== undefined && c.before !== null;
  const is = c.after !== undefined && c.after !== null && c.op !== "remove";
  return (
    <li className="history-change" data-field={c.field}>
      <span className="history-field">{where}</span>{" "}
      {is && was ? <><s className="history-before"><Brief name={c.field} v={c.before} /></s> → <Brief name={c.field} v={c.after} /></>
        : is ? <>set to <Brief name={c.field} v={c.after} /></>
        : was ? <>removed <span className="muted">(was <Brief name={c.field} v={c.before} />)</span></> : <span className="muted">{c.op}</span>}
    </li>
  );
}

export const HISTORY_PAGE = 25;

/** Its history, a page at a time: each event newest first, when, its kind, who wrote it, the move it made (from → to)
 *  and each field it changed (old → new); one that changed nothing says so; the event itself, whole, when opened. */
export function ItemHistory({ d }: { d: any }) {
  const [at, setAt] = useState(0);
  if (!d.history) return <Loading />;
  const all = historyOf(d);
  const page = all.slice(at, at + HISTORY_PAGE);
  const nothing = (x: Entry) => !x.move && !x.changes.length && !x.refused;
  return (
    <>
      {(d.record_total ?? 0) > (d.record || []).length && (
        <Note>The latest {(d.record || []).length} of its {d.record_total} events;{" "}
          <Link to={eventsHref(`item=${encodeURIComponent(d.id)}`)}>all of them in the Events</Link>.</Note>
      )}
      {d.transcript_events > 0 && (
        <Note>{d.transcript_events} more events are its transcript's lines (claude.*), folded into its fields;{" "}
          <Link to={eventsHref(`item=${encodeURIComponent(d.id)}`)}>all of them in the Events</Link>.</Note>
      )}
      {all.length > HISTORY_PAGE && <Pager total={all.length} offset={at} shown={page.length} size={HISTORY_PAGE} what="entries"
        onPage={(n) => setAt((n - 1) * HISTORY_PAGE)} />}
      {page.length ? (
        <ol className="item-history" aria-label="Its history, newest first">
          {page.map((x) => {
            const e = x.e, n = x.evs.length;
            return (
              <li key={e.id} id={`event-${e.id}`} className={`history-entry${nothing(x) ? " quiet" : ""}`} data-event={e.id}>
                <div className="history-head">
                  <span className="history-when nowrap">{n > 1 ? `${stamp(x.evs[n - 1].time)} to ${stamp(e.time)}` : stamp(e.time)}</span>{" "}
                  <b className="history-kind" title={e.type}>{eventName(e, d.projection)}</b>
                  {n > 1 && <span className="muted"> ×{n}</span>}
                  {e.source && <span className="muted history-by"> by {e.source}</span>}
                  {x.move && <span className="history-move" data-from={x.move.from || ""} data-to={x.move.to}>{" "}
                    <span className="stbox">{x.move.from || "arrived"}</span> → <span className="stbox on">{x.move.to}</span></span>}
                  {nothing(x) && <span className="muted small"> changed nothing</span>}
                </div>
                {x.changes.length > 0 && <ul className="history-changes">{x.changes.map((c, i) => <ChangeLine key={`${c.path}|${i}`} c={c} />)}</ul>}
                {x.refused && <p className="small lvl-warn history-refused">refused: {x.refused}</p>}
                <details className="history-raw">
                  <summary className="small muted">{n > 1 ? `the ${n} events` : "the event"}</summary>
                  {x.evs.map((y) => <pre key={y.id} className="small">{JSON.stringify(y, null, 2)}</pre>)}
                </details>
              </li>
            );
          })}
        </ol>
      ) : <Empty>No events.</Empty>}
      {d.rollup && (
        <Note>Its {d.rollup.archived?.events} oldest events, up to {stamp(d.rollup.last)}, are rolled up into one snapshot and archived.</Note>
      )}
    </>
  );
}
