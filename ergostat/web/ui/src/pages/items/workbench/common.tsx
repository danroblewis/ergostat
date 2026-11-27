import type { ReactNode } from "react";
import { JsonValues, type JsonPath, type PathMark } from "../../../components/JsonValues";
import { stamp } from "../../../lib/format";

/** An event as the query engine gives it (POST /api/events/query). */
export interface QEvent { seq: number; id: string; time: number; type: string; item: string | null; source: string | null; data: unknown }

export const n = (x: number | null | undefined) => (x == null ? "–" : x.toLocaleString());
export const short = (v: unknown, most = 60) => {
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s == null ? "" : s.length > most ? `${s.slice(0, most - 1)}…` : s;
};

/** One of the workbench's steps: a section with its number, its name, a line saying where it stands, and its body,
    which folds away (the others stay where they are: no step hides another). */
export function Step({ no, title, said, open, onToggle, children, id }: {
  no: number; title: string; said?: ReactNode; open: boolean; onToggle: () => void; children: ReactNode; id: string;
}) {
  return (
    <section className={`wb-step${open ? " open" : ""}`} aria-labelledby={`${id}-h`} data-step={no}>
      <h2 id={`${id}-h`} className="wb-step-head">
        <button type="button" className="ghost" aria-expanded={open} onClick={onToggle}>
          <span className="wb-no">{no}</span> {title}
        </button>
        {said && <span className="muted small wb-said">{said}</span>}
      </h2>
      {open && <div className="wb-step-body">{children}</div>}
    </section>
  );
}

/** The few short values that tell an event apart at a glance (the first strings, two levels into its data). */
const SAYS = /name|type|action|status|state|kind|event|op/i;   // names that say what happened come first
function telling(d: unknown): string[] {
  const found: [number, string][] = [];
  const walk = (v: unknown, depth: number) => {
    if (v == null || typeof v !== "object" || Array.isArray(v)) return;
    for (const [k, x] of Object.entries(v as Record<string, unknown>)) {
      if (typeof x === "string" && x.length <= 48 && !/^[\d.]*$/.test(x) && !/^[0-9a-f-]{20,}$/i.test(x) && !/^\d{4}-\d\d-\d\dT/.test(x)) {
        found.push([(SAYS.test(k) ? 0 : 2) + depth, x]);
      } else if (depth < 1) walk(x, depth + 1);
    }
  };
  walk(d, 0);
  return found.sort((a, b) => a[0] - b[0]).slice(0, 3).map(([, x]) => x);
}

/** An event's parts as the expressions name them (type, key, source, data), each value a button when `onPick`. */
export function EventValues({ e, onPick, picked, mark, showIgnored }: {
  e: QEvent; onPick?: (p: JsonPath, v: unknown) => void; picked?: string; mark?: (p: JsonPath) => PathMark | undefined; showIgnored?: boolean;
}) {
  const parts: [string, unknown][] = [["type", e.type], ["key", e.item], ["source", e.source], ["data", e.data]];
  return (
    <ul className="jv jv-top">
      {parts.filter(([k, v]) => v != null && (showIgnored || !mark?.([k])?.ignored)).map(([k, v]) => (
        <li key={k} className={mark?.([k])?.ignored ? "jv-ignored" : undefined}><span className="jv-key">{k}</span>{" "}
          <JsonValues value={v} path={[k]} onPick={onPick} picked={picked} mark={mark} showIgnored={showIgnored} /></li>
      ))}
    </ul>
  );
}

/** Events as a readable list: each its time, type and telling values, opened to its parts. */
export function EventList({ events, onPick, picked, open }: {
  events: QEvent[]; onPick?: (p: JsonPath, v: unknown) => void; picked?: string; open?: boolean;
}) {
  return (
    <ul className="wb-events">
      {events.map((e) => (
        <li key={e.id}>
          <details open={open}>
            <summary>
              <span className="muted small">{stamp(e.time)}</span> <code>{e.type}</code>{" "}
              {telling(e.data).map((t, i) => <span key={i} className="wb-tell">{t}</span>)}
            </summary>
            <EventValues e={e} onPick={onPick} picked={picked} />
          </details>
        </li>
      ))}
    </ul>
  );
}

/** A trimmed sample as the workbench sends it (an event's JSON, cut), shown as text. */
export const Samples = ({ samples }: { samples?: unknown[] }) =>
  samples?.length ? (
    <ul className="wb-samples">{samples.map((s, i) => <li key={i}><code>{typeof s === "string" ? s : JSON.stringify(s)}</code></li>)}</ul>
  ) : null;
