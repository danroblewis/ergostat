import { useEffect, useState, type ReactNode } from "react";
import { Button, Select } from "./ui";

/* Small controls every page and panel uses the same way: a segmented choice, a search box, a pager, the finished
   items' toggle, a page's label-value row under its title, and a group of things under its system. */

/** A choice of a few, side by side, one pressed (the old page's `.seg`). */
export function Segmented<T extends string>({ label, options, value, onChange, className }: {
  label: string; options: { value: T; label: ReactNode; title?: string }[]; value: T; onChange: (v: T) => void; className?: string;
}) {
  return (
    <span className={`seg${className ? ` ${className}` : ""}`} role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" className={o.value === value ? "on" : ""} aria-pressed={o.value === value}
          title={o.title} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </span>
  );
}

/** A search box: asked on Enter, or on each keystroke when `live`. It follows `value` when that changes elsewhere. */
export function SearchBox({ value = "", onSearch, live, placeholder = "Search", label = "Search" }: {
  value?: string; onSearch: (text: string) => void; live?: boolean; placeholder?: string; label?: string;
}) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  return (
    <input type="search" placeholder={placeholder} aria-label={label} value={text}
      onChange={(ev) => { setText(ev.target.value); if (live) onSearch(ev.target.value.trim()); }}
      onKeyDown={(ev) => { if (ev.key === "Enter") onSearch(text.trim()); }} />
  );
}

export const PAGE_SIZES = [25, 100, 300];

/** Pages of a long list: where it is, Prev and Next, and how many a page. `cut`: the list was sorted among the newest
 *  this many only (the server's). */
export function Pager({ at = "top", total, offset, shown, size, sizes = PAGE_SIZES, what = "", cut, onPage, onSize }: {
  at?: "top" | "foot"; total: number; offset: number; shown: number; size: number; sizes?: number[]; what?: string; cut?: number | null;
  onPage: (page: number) => void; onSize?: (size: number) => void;
}) {
  const reach = cut ? Math.min(total, cut) : total;
  const last = Math.max(1, Math.ceil(reach / size)), page = Math.floor(offset / size) + 1;
  return (
    <div className={`pager ${at}`} role="navigation" aria-label={`Pages, ${at}`}>
      <span className="pager-says">
        {offset + 1}-{offset + shown} of {total}{what ? ` ${what}` : ""}
        {cut ? <span className="muted">, sorted among the newest {cut}</span> : null}
      </span>
      {" · "}<Button variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>Prev</Button>
      {" · "}<Button variant="ghost" disabled={page >= last} onClick={() => onPage(page + 1)}>Next</Button>{" "}
      {onSize && (
        <Select aria-label="Rows a page" value={String(size)} onChange={(ev) => onSize(+ev.target.value)}
          options={sizes.map((x) => ({ value: String(x), label: `${x} a page` }))} />
      )}
    </div>
  );
}

/** Whether a list shows its finished items. */
export function FinishedToggle({ shown, onChange }: { shown: boolean; onChange: (shown: boolean) => void }) {
  return (
    <span className="fin-choice">
      <span className="muted">Finished items:</span>
      <Segmented label="Finished items" className="fin-seg" value={shown ? "show" : "hide"} onChange={(v) => onChange(v === "show")}
        options={[{ value: "hide", label: "Hidden" }, { value: "show", label: "Shown" }]} />
    </span>
  );
}

/** "N finished (done, dead) not shown · show": what a list left out, and the way to show it. */
export function FinishedNote({ n, states, onShow }: { n: number; states: string[]; onShow?: () => void }) {
  if (!n) return null;
  return (
    <p className="note finished-note">
      {n} finished ({states.join(", ")}) not shown
      {onShow && <>{" · "}<a href="#" className="finished-flip" onClick={(ev) => { ev.preventDefault(); onShow(); }}>show</a></>}
    </p>
  );
}

/** A thing's label-value row under its title (an item's projection, state, age; an agent's kind, system, schedule): a value
 *  that is empty leaves its label out. */
export function Meta({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <div className="meta">
      {rows.filter(([, v]) => v != null && v !== "" && v !== false).map(([k, v]) => <span key={k}><span>{k}</span>{v}</span>)}
    </div>
  );
}

/** Things under the system they are in: its name, a count, its description, then them. */
export function SystemGroup({ name, count, description, children, className }: {
  name: string; count?: ReactNode; description?: string; children: ReactNode; className?: string;
}) {
  return (
    <section className={`sys-group${className ? ` ${className}` : ""}`} data-system={name}>
      <h2 className="sys-head">
        {name}
        {count != null && <span className="muted"> {count}</span>}
        {description && <span className="muted sys-desc">{description}</span>}
      </h2>
      {children}
    </section>
  );
}
