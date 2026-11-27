import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ago, dur, fmt, nowS, plural, stamp, timeField } from "../lib/format";
import { itemHref, projectionHref } from "../lib/hrefs";
import { Segmented } from "./controls";
import { Markdown } from "./Markdown";
import { Table } from "./Table";

/* Items, the same on every page (kinds.js, pages.js pageItems): a projection's bar, a field's value, and a table of items.
   A projection's flow chart is charts/FlowChart; an item's events, events.tsx. */

/** The states a list leaves out unless shown: a projection's finished and dead, none for one that lives on. */
export const hiddenStates = (k: any): string[] => (!k || k.lives_on ? [] : [...(k.finished || []), ...(k.dead ? ["dead"] : [])]);

/** A projection's bar (kinds.js kindBar): title, id pattern, total, description, its state chips with counts, how it ends. */
export function ProjectionBar({ k, level = 3, state, onState, open, onOpen }: {
  k: any; level?: 1 | 2 | 3; state?: string | null; onState?: (st: string | null) => void; open?: boolean; onOpen?: () => void;
}) {
  const counts: Record<string, number> = k.counts || {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const fin = k.lives_on ? "lives on" : k.finished?.length ? `finishes: ${k.finished.join(", ")}` : null;
  const H = `h${level}` as "h1" | "h2" | "h3";
  const states: string[] = k.states?.length ? k.states : [""];
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
        <span className="muted projection-total"> {plural(total, "item")}</span>
      </H>
      {k.description && <p className="projection-desc">{k.description}</p>}
      <div className="states">
        {states.map((st, i) => (
          <span key={st || "-"}>
            {i > 0 && <span className="arrow" aria-hidden="true">→</span>}
            <a
              href={`${projectionHref(k.name, st ? `state=${encodeURIComponent(st)}` : "")}`}
              className={`stbox${counts[st] ? " some" : ""}${st && state === st ? " on" : ""}`}
              aria-pressed={!!st && state === st}
              onClick={(ev) => { ev.preventDefault(); onState?.(st && state === st ? null : st || null); }}
            >
              <span className="n">{String(counts[st] || 0)}</span>
              {st || "items"}
            </a>
          </span>
        ))}
      </div>
      <p className="muted small projection-says">
        {fin}
        {fin && k.system ? " · " : null}
        {k.system && <span className="projection-sys" title={k.system_why || ""}>in {k.system}</span>}
      </p>
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
            <Table.Td className="nowrap"><Link to={itemHref(i.id, undefined, i.projection)} className="plain"><b>{i.id}</b></Link></Table.Td>
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
