import { Fragment, type ReactNode, type ButtonHTMLAttributes, type InputHTMLAttributes, type SelectHTMLAttributes } from "react";
import { Link, type LinkProps } from "react-router-dom";
import { RUNG_HINT, RUNG_LETTER, rungName } from "../lib/rung";

/* The small parts every page is built from. Each keeps the old page's class names, so style.css draws them. */

/** A page: its title, what it offers beside the title (``actions``), and its body. */
export function Page({ title, actions, children, className }: { title: ReactNode; actions?: ReactNode; children?: ReactNode; className?: string }) {
  return (
    <div className={`page ${className ?? ""}`.trim()}>
      <h1>
        {title}
        {actions && <span className="page-actions">{actions}</span>}
      </h1>
      {children}
    </div>
  );
}

/** A part of a page under its heading; ``note`` muted after it. */
export function Section({ title, note, children, id, className }: { title: ReactNode; note?: ReactNode; children?: ReactNode; id?: string; className?: string }) {
  return (
    <section id={id} className={className}>
      <h2>
        {title}
        {note && <> <span className="muted">{note}</span></>}
      </h2>
      {children}
    </section>
  );
}

/** A link to one of the app's own pages ("/goals"), drawn in place with no reload. */
export const AppLink = (props: LinkProps) => <Link {...props} />;

/** A definition list that leaves out empty values; nothing at all when every value is empty. */
export function Dl({ rows, className }: { rows: [ReactNode, ReactNode][]; className?: string }) {
  const kept = rows.filter(([, v]) => v != null && v !== "" && v !== false);
  if (!kept.length) return null;
  return (
    <dl className={className}>
      {kept.map(([k, v], i) => <Fragment key={i}><dt>{k}</dt><dd>{v}</dd></Fragment>)}
    </dl>
  );
}

export const Muted = ({ children, small }: { children: ReactNode; small?: boolean }) => (
  <span className={small ? "muted small" : "muted"}>{children}</span>
);
export const Note = ({ children }: { children: ReactNode }) => <p className="note">{children}</p>;
export const Empty = ({ children }: { children: ReactNode }) => <p className="empty">{children}</p>;
export const Loading = ({ what = "Loading" }: { what?: string }) => <p className="muted" aria-busy="true">{what}…</p>;
export function ErrorNote({ error }: { error: Error | string | null | undefined }) {
  if (!error) return null;
  return <p className="note lvl-error" role="alert">{typeof error === "string" ? error : error.message}</p>;
}

/** What an API answer is while it comes: loading, failed, or its content. */
export function Async<T>({ state, children, what }: {
  state: { data: T | undefined; error: Error | null };
  children: (data: T) => ReactNode;
  what?: string;
}) {
  if (state.data === undefined) return state.error ? <ErrorNote error={state.error} /> : <Loading what={what} />;
  return (
    <>
      {state.error && <ErrorNote error={state.error} />}
      {children(state.data)}
    </>
  );
}

/** A goal's state as a word: quiet when it holds, coloured only when it needs someone. */
export const StatusWord = ({ status }: { status?: string | null }) => (
  <span className={`status s-${status || "unknown"}`}>{status || "unknown"}</span>
);

/** An agent's rung: its kind in words and a letter, never colour alone (invariant 4). */
export function Rung({ rung, retired }: { rung: number | null | undefined; retired?: boolean }) {
  const r = retired ? 6 : rung ?? null;
  return (
    <span className="rung" title={r == null ? undefined : RUNG_HINT[r]}>
      <span className="rung-letter" aria-hidden="true">{r == null ? "?" : RUNG_LETTER[r]}</span>{" "}
      {retired ? "retired" : rungName(rung)}
    </span>
  );
}

export function Button({ variant, className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "ghost" | "name" | "on" }) {
  return <button type="button" className={[variant, className].filter(Boolean).join(" ") || undefined} {...rest} />;
}

export function Select({ options, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & {
  options: (string | { value: string; label: ReactNode; disabled?: boolean; title?: string })[];
}) {
  return (
    <select {...rest}>
      {options.map((o) =>
        typeof o === "string"
          ? <option key={o} value={o}>{o}</option>
          : <option key={o.value + String(o.label)} value={o.value} disabled={o.disabled} title={o.title}>{o.label}</option>,
      )}
    </select>
  );
}

export function Check({ label, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  return (
    <label className="check">
      <input type="checkbox" {...rest} /> {label}
    </label>
  );
}

/** A row of filters above a list (div.filters). */
export const Filters = ({ children }: { children: ReactNode }) => <div className="filters">{children}</div>;

/** A fold: summary shown, the rest when opened. */
export function Fold({ summary, children, open, className }: { summary: ReactNode; children: ReactNode; open?: boolean; className?: string }) {
  return (
    <details className={className} open={open}>
      <summary>{summary}</summary>
      {children}
    </details>
  );
}

/** Tabs: one is on; choosing another calls ``onChange``. Rendered as buttons in a tablist. */
export function Tabs<K extends string>({ tabs, value, onChange, label }: {
  tabs: { key: K; label: ReactNode; title?: string }[];
  value: K;
  onChange: (k: K) => void;
  label: string;
}) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={t.key === value}
          className={t.key === value ? "on" : undefined}
          title={t.title}
          onClick={() => onChange(t.key)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

const SUB = /([A-Za-zͰ-Ͽ])_(\{[^}]+\}|[A-Za-z0-9]+)/g;
/** K_p, y_m, x_{ab}: a subscript as a subscript. */
export function Rich({ text }: { text: unknown }) {
  const str = String(text ?? "");
  const out: ReactNode[] = [];
  let at = 0;
  for (const m of str.matchAll(SUB)) {
    out.push(str.slice(at, m.index) + m[1], <sub key={m.index}>{m[2].replace(/^\{|\}$/g, "")}</sub>);
    at = m.index! + m[0].length;
  }
  out.push(str.slice(at));
  return <span>{out}</span>;
}
