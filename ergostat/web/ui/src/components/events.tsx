import { useCallback, type ReactNode } from "react";
import { stamp } from "../lib/format";
import { useDetail } from "./Detail";
import { ItemLink } from "./links";
import { Fields, Table } from "./Table";

/* The record's events, the same on every page (details.js eventsTable): a table newest first, where a run of
   identical events in a row may fold into one row (×n), and a click shows an event whole in the side panel. */

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

/** One event whole: what the side panel shows when an event is clicked. */
export function EventDetail({ e }: { e: RecordEvent }) {
  const fields = (
    [
      ["item", e.item ? <ItemLink id={e.item} remote={e.remote} /> : null],
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

/** Opens an event in the side panel: `const show = useShowEvent(); show(e)`. */
export function useShowEvent(): (e: RecordEvent) => void {
  const { open } = useDetail();
  return useCallback((e: RecordEvent) => open(`event:${e.id}`, <EventDetail e={e} />), [open]);
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

/** Events (oldest first, as the API gives them) drawn newest first. `compact`: no item column (they are all one
 *  item's). `fold`: a run of identical events in a row is one row, its events listed in the side panel. */
export function EventsTable({ events, compact, fold, caption = "Events, newest first" }: {
  events: RecordEvent[]; compact?: boolean; fold?: boolean; caption?: string;
}) {
  const detail = useDetail();
  const show = useShowEvent();
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
        <EventsTable events={run.slice().reverse()} compact={compact} />
      </>
    ));
  return (
    <Table caption={caption}>
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
                    else show(e);
                  }}
                >
                  {e.type}
                </a>
                {n > 1 && <span className="run-count">{` ×${n}`}</span>}
              </td>
              {!compact && <td className="nowrap"><ItemLink id={e.item} remote={e.remote} /></td>}
              <td className="muted nowrap">{e.source || "–"}</td>
              <DataCell d={changeOf(e)} />
            </tr>
          );
        })}
      </Table.Body>
    </Table>
  );
}
