import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { Async, Empty, EventsTable, FieldValue, Loading, Note, Page, Table, isShort, useShowEvent } from "../../components";
import { itemHref, kindHref } from "../../lib/hrefs";
import { useApi } from "../../hooks/useApi";
import { ago, dur, nowS, stamp } from "../../lib/format";
import { useTime } from "../../state/time";

/* /item/ID (pages.js pageItem): why it is not done, its kind, state, age and events; the path it took through its
   states; its relations both ways; its fields (its kind's chosen first, a long one as Markdown); how it moved; its
   events; and each field's changes, asked for when the Changes fold is opened. */

const CHANGES_SHOWN = 200;

export default function ItemPage() {
  const { id = "" } = useParams();
  const { at } = useTime();
  const [changesOf, setChangesOf] = useState<string | null>(null);   // null: Changes folded; "": every field's
  const item = useApi<any>(`items/${encodeURIComponent(id)}`, changesOf != null ? { history: changesOf || "all" } : {}, { every: 4000 });
  const d = item.data;
  const final: string[] = d?.kind_of?.final || [];
  const why = useApi<any>(d && !at && d.state && !final.includes(d.state) ? "why" : null, { item: id }, { every: 10000, window: false });
  return (
    <Page title={id}>
      {item.error && !d ? (
        <p className="muted">Nothing is recorded about this id.</p>
      ) : (
        <Async state={item}>
          {(d) => <ItemBody d={d} why={why.data} changesOf={changesOf} setChangesOf={setChangesOf} />}
        </Async>
      )}
    </Page>
  );
}

function ItemBody({ d, why, changesOf, setChangesOf }: {
  d: any; why: any; changesOf: string | null; setChangesOf: (f: string | null) => void;
}) {
  const k = d.kind_of;
  const now = nowS();
  const showEvent = useShowEvent();
  const eventLink = (eid: string, type: string) => {
    const e = (d.record || []).find((x: any) => x.id === eid);
    return e ? <a href="#" className="plain" title={`event ${eid}`} onClick={(ev) => { ev.preventDefault(); showEvent(e); }}>{type}</a> : <span>{type}</span>;
  };
  const pair = (label: string, value: ReactNode) => <span key={label}><span>{label}</span>{value}</span>;

  // the path it took, arrow by arrow, to where it is now; the other states apart (its endings double-bordered)
  const fin = new Set<string>(k?.final || []);
  const path: string[] = d.moves.map((m: any) => m.to).filter((s: string, i: number, a: string[]) => s && s !== a[i - 1]);
  if (d.state && path[path.length - 1] !== d.state) path.push(d.state);
  const ended = fin.has(d.state);
  const rest: string[] = (k?.states || []).filter((s: string) => !path.includes(s) && (!ended || fin.has(s)));
  const box = (st: string) => <span key={st} className={`stbox${st === d.state ? " on" : ""}${fin.has(st) ? " final" : ""}`}>{st}</span>;
  const counted = !!d.path?.some((st: any) => st.stock || st.flow || st.block);
  const toDiagram = (view: string, by: string, v: string) => `/diagram?view=${view}&${by}=${encodeURIComponent(v)}`;

  // its kind's chosen fields first, in their order, then the rest by name; removed ones still have changes
  const counts: Record<string, number> = d.changes || {};
  const first: string[] = (k?.show || []).filter((f: string) => f in d.fields);
  const gone = Object.keys(counts).filter((f) => f && !(f in d.fields));
  const order = [...first, ...Object.keys(d.fields).filter((f) => !first.includes(f)).sort(), ...gone.sort()].filter((f) => f !== "lease");
  const grid = order.filter((f) => !(f in d.fields) || isShort(d.fields[f]));
  const fname = (f: string) => (
    <>
      {f}
      {k?.fold?.[f] && <span className="muted small rule" title="how its events' data folds into it"> {k.fold[f]}</span>}
      {counts[f] > 1 && (
        <a className="small changes-of" href="#changes" onClick={(ev) => { ev.preventDefault(); setChangesOf(f); document.getElementById("changes")?.scrollIntoView(); }}>
          {" "}{counts[f]} changes
        </a>
      )}
    </>
  );

  return (
    <div>
      {why && why.known && !why.done && (
        <div className="note why" data-why={why.root ? why.root.kind : "unknown"}>
          <b>Why isn't this done? </b>{why.summary}
          {why.root?.command && <p><span className="muted">{why.root.owner}: </span><code>{why.root.command}</code></p>}
          {why.evidence?.length > 0 && (
            <ul className="small">
              {why.evidence.slice(0, 6).map((e: any) => <li key={`${e.says}|${e.link}`}>{e.link ? <a href={e.link}>{e.says}</a> : e.says}</li>)}
            </ul>
          )}
        </div>
      )}

      <div className="meta">
        {pair("Kind", k ? <Link to={kindHref(k.name)}>{k.name}</Link> : <span className="muted">none (nothing under items: matches this id)</span>)}
        {d.state && pair("State", <span><b>{d.state}</b> for {dur(now - d.entered)}</span>)}
        {d.eta?.unscheduled
          ? pair("Expected done", <span data-eta="">not scheduled: {d.eta.said || "it cannot move"}</span>)
          : d.eta?.p50 && pair("Expected done", <span data-eta=""><b>{stamp(d.eta.p50)}</b>{d.eta.p90 ? <span className="muted"> (90% by {stamp(d.eta.p90)})</span> : null}</span>)}
        {pair("Events", String(d.events))}
        {pair("First", ago(d.first))}
        {pair("Latest", <span>{d.latest}<span className="muted">, {ago(d.last)}</span></span>)}
      </div>

      {k && k.states?.length > 0 && (
        <>
          <h2>Where it went</h2>
          <div className="track">
            {path.map((st, i) => <span key={st + i}>{i > 0 && <span className="arrow" aria-hidden="true">→</span>}{box(st)}</span>)}
            {rest.length > 0 && <span className="alt">{ended ? "could also have ended:" : "its other states:"}{rest.map(box)}</span>}
          </div>
          {d.path && (counted ? (
            <p className="went">
              <a href={toDiagram("dynamics", "item", d.id)}>Draw its path in Dynamics</a>, <a href={toDiagram("blocks", "item", d.id)}>in Blocks</a>
              {k && <>; <a href={toDiagram("dynamics", "kind", k.name)}>what every {k.name} touches</a></>}.
            </p>
          ) : <p className="went muted uncounted">Its moves are not counted anywhere in the model.</p>)}
          {d.path?.some((p: any) => p.says) && (
            <ul className="small muted">{d.path.filter((p: any) => p.says).map((p: any) => <li key={p.state}>{p.says}</li>)}</ul>
          )}
        </>
      )}

      {d.eta?.why && <p className="note eta-why">{d.eta.waits_in && <b>Waiting in {d.eta.waits_in}: </b>}{d.eta.why}</p>}

      {d.relations && <Relations r={d.relations} k={k} />}

      <h2>Fields</h2>
      {order.length ? (
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
      ) : <p className="muted">No fields: its events carry no data.</p>}

      {d.refused?.length > 0 && (
        <>
          <h2>Refused</h2>
          <Note>Events recorded that changed nothing: their changeset could not apply, so none of it did.</Note>
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
        </>
      )}

      <h2>How it moved</h2>
      {d.moves.length ? (
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
      ) : <p className="muted">Its kind has no states.</p>}

      <h2>Events <span className="muted">{d.events}</span></h2>
      {d.transcript_events > 0 && (
        <Note>
          {d.transcript_events} more events are its transcript's lines (claude.*), folded into its fields above;{" "}
          <Link to={`/record?item=${encodeURIComponent(d.id)}`}>all of them in the Record</Link>.
        </Note>
      )}
      {d.rollup && (
        <Note>Its {d.rollup.archived?.events} oldest events, up to {stamp(d.rollup.last)}, are rolled up into one snapshot and archived.</Note>
      )}
      {d.record?.length ? <EventsTable events={d.record} compact /> : <Empty>No events.</Empty>}

      <details className="history changes" id="changes" open={changesOf != null}
        onToggle={(ev) => { const open = (ev.target as HTMLDetailsElement).open; if (open !== (changesOf != null)) setChangesOf(open ? "" : null); }}>
        <summary><h2>Changes <span className="muted">{Object.values(counts).reduce((a, b) => a + b, 0)}</span></h2></summary>
        {changesOf != null && <History d={d} of={changesOf} all={() => setChangesOf("")} eventLink={eventLink} />}
      </details>
    </div>
  );
}

/** Its relations both ways (pages.js relationsView): what it names, and what names it, each related item's state. */
function Relations({ r, k }: { r: any; k: any }) {
  const rows: [string, string[], any][] = [
    ...Object.entries<string[]>(r.out || {}).map(([n, ids]) => [n, ids, r.relations?.[n]] as [string, string[], any]),
    ...Object.entries<string[]>(r.in || {}).map(([n, ids]) => [n, ids, null] as [string, string[], any]),
  ];
  if (!rows.length) return null;
  return (
    <>
      <h2>Relations</h2>
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
      {k && <Note>All of them in <a href={`${kindHref(k.name, "view=graph")}`}>the graph</a>.</Note>}
    </>
  );
}

/** The Changes fold's body (pages.js historyView): each field's changes, the latest first. */
function History({ d, of, all, eventLink }: { d: any; of: string; all: () => void; eventLink: (eid: string, type: string) => ReactNode }) {
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
        {of ? <>The changes to {of}; <a href="#changes" onClick={(ev) => { ev.preventDefault(); all(); }}>every field's</a>.</> : "Each field's changes, the latest first."}
        {rows.length < total && <> The latest {CHANGES_SHOWN} of a field's; <code>ergostat item {d.id} --history</code> lists all.</>}
      </Note>
      {rows.length ? (
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
      ) : <p className="muted">No changes.</p>}
    </>
  );
}
