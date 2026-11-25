import { type ReactNode } from "react";
import { AppLink, Fields, Table } from "../../components";
import { useDetail } from "../../components";
import { stamp } from "../../lib/format";

/* The record's events as a table, newest first (details.js eventsTable): folded, a run of identical events in a row
   is one row (×n), listed in the side panel when clicked; one event, clicked, shows all of it there. Kept in this
   folder: the item and agent pages draw their own events, and could move this to components/ when both need it. */

export interface RecordEvent {
  seq?: number;
  id: string;
  time: number;
  type: string;
  item?: string | null;
  source?: string | null;
  causedby?: string | null;
  data?: Record<string, unknown>;
  patch?: unknown;
  set?: unknown;
  remote?: string;
}

/** What an event says of its item: its data, or the JSON Patch or whole document it carries (SPEC §5a). */
export const changeOf = (e: RecordEvent): unknown => (e.patch ? { patch: e.patch } : e.set ? { set: e.set } : e.data || {});

/* the ids that may be opened on a remote: as remote/items.py's openable, an allowlist (/-separated segments, no "..") */
const REMOTE_ID = /^[A-Za-z0-9_][A-Za-z0-9_.:@#+=-]*(\/[A-Za-z0-9_][A-Za-z0-9_.:@#+=-]*)*$/;
export function ItemLink({ e }: { e: RecordEvent }): ReactNode {
  if (!e.item) return "–";
  if (e.remote) {
    const ok = e.item.length <= 200 && REMOTE_ID.test(e.item) && !e.item.includes("..");
    return ok ? <AppLink to={`/item/${encodeURIComponent(e.item)}?remote=${encodeURIComponent(e.remote)}`}>{e.item}</AppLink> : e.item;
  }
  return <AppLink to={`/item/${encodeURIComponent(e.item)}`}>{e.item}</AppLink>;
}

function DataCell({ d }: { d: unknown }) {
  const flat = JSON.stringify(d || {});
  if (flat === "{}") return <td className="mono muted" />;
  if (flat.length <= 110) return <td className="mono muted data">{flat}</td>;
  return (
    <td className="mono muted data">
      <details>
        <summary>{flat.slice(0, 100) + "…"}</summary>
        <pre>{JSON.stringify(d, null, 2)}</pre>
      </details>
    </td>
  );
}

function EventDetail({ e }: { e: RecordEvent }) {
  const fields: [ReactNode, ReactNode][] = (
    [
      ["item", e.item ? <ItemLink e={e} /> : null],
      ["source", e.source],
      ["when", stamp(e.time)],
      ["id", e.id],
      ["caused by", e.causedby],
    ] as [ReactNode, ReactNode][]
  ).filter(([, v]) => v != null && v !== "");
  return (
    <>
      <div className="kind">{e.remote ? `Event, remote ${e.remote}` : "Event"}</div>
      <h2>{e.type}</h2>
      <Fields caption="The event" fields={fields} />
      <pre>{JSON.stringify(changeOf(e), null, 2)}</pre>
    </>
  );
}

export function EventsTable({ events, compact, fold }: { events: RecordEvent[]; compact?: boolean; fold?: boolean }) {
  const detail = useDetail();
  const runs: { sig: string; evs: RecordEvent[] }[] = [];
  for (const e of events.slice().reverse()) {
    const last = runs[runs.length - 1];
    const sig = JSON.stringify([e.type, e.source, e.item, changeOf(e)]);
    if (fold && last && last.sig === sig) last.evs.push(e);
    else runs.push({ sig, evs: [e] });
  }
  const showRun = (run: RecordEvent[]) =>
    detail.open(`run:${run[0].id}`, (
      <>
        <div className="kind">Events in a row</div>
        <h2>{`${run[0].type} ×${run.length}`}</h2>
        <EventsTable events={run.slice().reverse()} />
      </>
    ));
  return (
    <Table caption="Events, newest first">
      <Table.Head>
        <Table.Th>when</Table.Th>
        <Table.Th>type</Table.Th>
        {!compact && <Table.Th>item</Table.Th>}
        <Table.Th>source</Table.Th>
        <Table.Th>data</Table.Th>
      </Table.Head>
      <Table.Body>
        {runs.map(({ evs: run }) => {
          const e = run[0];
          const n = run.length;
          return (
            <tr key={e.id} className={detail.key === `event:${e.id}` || detail.key === `run:${e.id}` ? "selected" : undefined}>
              <td className="nowrap">{n > 1 ? `${stamp(run[n - 1].time)}–${stamp(e.time)}` : stamp(e.time)}</td>
              <td className="nowrap">
                <a
                  href="#"
                  className="plain"
                  title={n > 1 ? `${n} events in a row: list them` : `event ${e.id}`}
                  onClick={(ev) => {
                    ev.preventDefault();
                    if (n > 1) showRun(run);
                    else detail.open(`event:${e.id}`, <EventDetail e={e} />);
                  }}
                >
                  {e.type}
                </a>
                {n > 1 && <span className="run-count">{` ×${n}`}</span>}
              </td>
              {!compact && <td className="nowrap"><ItemLink e={e} /></td>}
              <td className="muted nowrap">{e.source || "–"}</td>
              <DataCell d={changeOf(e)} />
            </tr>
          );
        })}
      </Table.Body>
    </Table>
  );
}
