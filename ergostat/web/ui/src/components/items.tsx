import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ago, dur, fmt, nowS, plural, stamp, timeField } from "../lib/format";
import { itemHref, projectionHref, routeTable, scopeHref } from "../lib/hrefs";
import { Segmented } from "./controls";
import { StateGraph } from "./StateGraph";
import { Markdown } from "./Markdown";
import { Table } from "./Table";

/* Items, the same on every page (kinds.js, pages.js pageItems): a projection's bar, a field's value, and a table of items.
   A projection's flow chart is charts/FlowChart; an item's events, events.tsx. */

/** The states a list leaves out unless shown: a projection's finished and dead, none for one that lives on. */
export const hiddenStates = (k: any): string[] => (!k || k.lives_on ? [] : [...(k.finished || []), ...(k.dead ? ["dead"] : [])]);

/** A projection's bar (kinds.js kindBar), the projection-summary panel's body: title, id pattern, total, description,
    the system it is in (a link to that system). Its graph of states is the projection-states panel's (ProjectionGraph). */
export function ProjectionBar({ k, level = 3, open, onOpen }: {
  k: any; level?: 1 | 2 | 3; open?: boolean; onOpen?: () => void;
}) {
  const total = Object.values<number>(k.counts || {}).reduce((a, b) => a + b, 0);
  const ends = hiddenStates(k);                          // how many are not finished (the Inbox's: those waiting)
  const unfinished = ends.length ? Object.entries<number>(k.counts || {}).filter(([s]) => !ends.includes(s)).reduce((a, [, n]) => a + n, 0) : null;
  const H = `h${level}` as "h1" | "h2" | "h3";
  const sys = k.system && routeTable()?.scopes?.[k.system] ? scopeHref(k.system) : null;
  return (
    <div className="projection-bar" data-projection={k.name}>
      <H className="projection-title">
        {onOpen && (
          <button type="button" className="ghost disclose" aria-expanded={!!open}
            aria-label={open ? `Hide the ${k.name} items` : `Show the ${k.name} items`} onClick={onOpen}>
            <span className="tri" aria-hidden="true">{open ? "▾" : "▸"}</span>
          </button>
        )}
        <Link to={projectionHref(k.name)} className="kname">
          {k.title || k.name}
          {k.title && <span className="mono">{k.name}</span>}
        </Link>
        <span className="muted small mono projection-id">{k.id || ""}</span>
        <span className="muted projection-total"> {plural(total, "item")}{unfinished != null && total ? `, ${unfinished} not finished` : ""}</span>
        {k.system && (sys
          ? <Link to={sys} className="small projection-sys" title={k.system_why || `the system ${k.system}`}>{k.system}</Link>
          : <span className="muted small projection-sys" title={k.system_why || ""}>{k.system}</span>)}
      </H>
      {k.description && <p className="projection-desc">{k.description}</p>}
    </div>
  );
}

/** A projection's graph of states, the projection-states panel's body (StateGraph: each state's count now, the moves
    made between them, its ends boxed double); one without states, its total alone. */
export function ProjectionGraph({ k, state, onState, counts = true }: {
  k: any; state?: string | null; onState?: (st: string | null) => void; counts?: boolean;
}) {
  const total = Object.values<number>(k.counts || {}).reduce((a, b) => a + b, 0);
  return (
    <div className="projection-states" data-projection={k.name}
      title={k.lives_on ? "it lives on: no state finishes it" : k.finished?.length ? `finishes: ${k.finished.join(", ")}` : undefined}>
      {k.states?.length ? <StateGraph k={k} state={state} onState={onState} counts={counts} /> : (
        <div className="states">
          <Link to={projectionHref(k.name)} className={`stbox${total ? " some" : ""}`}
            onClick={(ev) => { if (onState) { ev.preventDefault(); onState(null); } }}>
            {counts && <span className="n">{String(total)}</span>}items
          </Link>
        </div>
      )}
    </div>
  );
}

/** A field's value, shortly: a time as a stamp, a number formatted, an object as JSON, a long text as Markdown. */
export function FieldValue({ name, value, cell }: { name: string; value: unknown; cell?: boolean }): ReactNode {
  if (value == null || value === "") return <span className="muted">–</span>;
  const t = timeField(name, value);
  if (t) return <span title={String(value)}>{t}</span>;
  if (typeof value === "number") return <>{fmt(value)}</>;
  if (typeof value === "boolean") return <>{String(value)}</>;
  if (typeof value === "string") {
    if (/^https?:\/\//.test(value)) return <a href={value} target="_blank" rel="noopener noreferrer">{cell ? short(value) : value}</a>;
    if (/^[a-z][\w.-]*\/[\w.-]+$/i.test(value) && !cell) return <>{value}</>;
    if (cell) return <>{short(value)}</>;
    return value.length > 60 || value.includes("\n") ? <Markdown source={value} /> : <>{value}</>;
  }
  const json = JSON.stringify(value, null, cell ? 0 : 2);
  return cell ? <span className="mono small">{short(json)}</span> : <pre>{json}</pre>;
}
const short = (s: string, n = 80) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

export const isShort = (v: unknown) =>
  v == null || v === "" || typeof v === "number" || typeof v === "boolean" || (typeof v === "string" && v.length <= 60 && !v.startsWith("file:") && !v.includes("\n"));

const isNum = (its: any[], f: string) =>
  its.some((i) => typeof i.fields?.[f] === "number") && its.every((i) => i.fields?.[f] == null || typeof i.fields[f] === "number");

/** One projection's items under its chosen fields (pages.js tableOf): a header's click sorts by that field. */
export function ItemsTable({ items, show, sort, onSort, caption }: {
  items: any[]; show: string[]; sort?: string; onSort?: (s: string) => void; caption: string;
}) {
  const fields = show.filter((f) => f !== "lease");
  const nums = new Set(fields.filter((f) => isNum(items, f)));
  const by = (sort || "").replace(/^-/, ""), down = (sort || "").startsWith("-");
  const etaCol = items.some((i) => i.eta);
  const head = (f: string) =>
    onSort ? (
      <button type="button" className="ghost sort" title={`Sort by ${f}`} aria-label={`Sort by ${f}`}
        data-sort={by === f ? (down ? "descending" : "ascending") : "none"}
        onClick={() => onSort(by !== f ? f : !down ? `-${f}` : "")}>
        {f}{by === f && <span aria-hidden="true">{down ? " ▾" : " ▴"}</span>}
      </button>
    ) : f;
  const now = nowS();
  return (
    <Table caption={caption} className="items projection-items">
      <Table.Head>
        <Table.Th>item</Table.Th>
        <Table.Th>state</Table.Th>
        {fields.map((f) => (
          <Table.Th key={f} num={nums.has(f)} sort={by === f ? (down ? "descending" : "ascending") : undefined}>{head(f)}</Table.Th>
        ))}
        {etaCol && <Table.Th num>done by</Table.Th>}
        <Table.Th num className="keep">in state</Table.Th>
        <Table.Th num>events</Table.Th>
        <Table.Th>latest</Table.Th>
        <Table.Th>last</Table.Th>
      </Table.Head>
      <Table.Body>
        {items.map((i) => (
          <Table.Row key={`${i.projection}:${i.id}`} to={itemHref(i.id, undefined, i.projection)}>
            <Table.Td className="nowrap">
              <Link to={itemHref(i.id, undefined, i.projection)} className="plain" title={i.name ? i.id : undefined}><b>{i.name || i.id}</b></Link>
              {i.name && <span className="muted small item-key"> {i.id}</span>}
            </Table.Td>
            <Table.Td className="nowrap">{i.state || <span className="muted">–</span>}</Table.Td>
            {fields.map((f) => (
              <Table.Td key={f} num={nums.has(f)} className={nums.has(f) ? undefined : "cell"}
                title={i.fields?.[f] == null ? "" : typeof i.fields[f] === "object" ? JSON.stringify(i.fields[f]) : String(i.fields[f])}>
                <FieldValue name={f} value={i.fields?.[f]} cell />
              </Table.Td>
            ))}
            {etaCol && <Table.Td num className="nowrap">{i.eta?.p50 ? ago(2 * now - i.eta.p50).replace(" ago", "") : ""}</Table.Td>}
            <Table.Td num className="nowrap keep">{i.state ? dur(now - i.entered) : ""}</Table.Td>
            <Table.Td num>{String(i.events)}</Table.Td>
            <Table.Td className="muted">{i.latest}</Table.Td>
            <Table.Td className="muted nowrap" title={stamp(i.last)}>{ago(i.last)}</Table.Td>
          </Table.Row>
        ))}
      </Table.Body>
    </Table>
  );
}

/** A projection's states as their groups (waiting, working, stopped, done) or each its own. */
export function StatesChoice({ all, onChange }: { all: boolean; onChange: (all: boolean) => void }) {
  return (
    <Segmented label="States" value={all ? "all" : "groups"} onChange={(v) => onChange(v === "all")} options={[
      { value: "groups", label: "State groups", title: "Each projection's states as waiting, working, stopped and done" },
      { value: "all", label: "Every state", title: "Each projection's own states" },
    ]} />
  );
}
