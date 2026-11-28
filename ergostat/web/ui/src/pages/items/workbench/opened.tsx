import { n, short, type QEvent } from "./common";

/* A residual group opened in the mapping step (SPEC §5a, *The page*): events with no key of one kind, events refused
   for one reason, or a possible split's object. The review's residual gives each group's events whole; the kinds that
   took them show those events as their samples, what is wrong highlighted, until the group is fixed (gone from a
   review of a draft that checks), when the banner says so and the kinds return to their usual samples. */

/** `in`: the kinds it is shown in; `was`: its count when opened; `token`: a new one each time it is opened (scrolled to). */
export type Opened = { in: string[]; was: number; token: number } & (
  | { what: "no_key"; kind: string }
  | { what: "refused"; field?: string; value?: unknown; why: string }
  | { what: "split"; kinds: string[] });

/** An event the residual gives whole: the kind that took it, and (a split's) the object it went to. */
export type OpenedEvent = QEvent & { kind?: string | null; object?: string };

/** What a group opened is now, in a review: its count, its events, what to highlight. */
export interface Live {
  count: number; events: OpenedEvent[];
  /** key fields to highlight and to focus the mapping of; those of them the kind does not tell */
  key: string[]; untold: string[];
  /** a field refused, the value, and why */
  field?: string; value?: unknown; why?: string;
  objects?: string[];
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** The group in this review (null: it is gone, fixed). */
export function liveOf(r: any, o: Opened): Live | null {
  const s = r?.residual;
  if (!s) return null;
  if (o.what === "no_key") {
    const g = (s.no_key?.groups || []).find((x: any) => x.kind === o.kind);
    return g ? { count: g.count, events: g.events || [], key: [...g.lacks, ...g.no_value.filter((f: string) => !g.lacks.includes(f))], untold: g.lacks } : null;
  }
  if (o.what === "refused") {
    const g = (s.refused?.groups || []).find((x: any) => (o.field != null ? x.field === o.field && same(x.value, o.value) : x.why === o.why));
    return g ? { count: g.count, events: g.samples || [], key: [], untold: [], field: g.field, value: g.value, why: g.why } : null;
  }
  const g = (s.splits?.groups || []).find((x: any) => same(x.kinds, o.kinds));
  return g ? { count: g.objects, events: g.events || [], key: g.differ || [], untold: [], objects: [g.samples?.[0], g.twin].filter(Boolean) } : null;
}

const kindsOf = (evs: OpenedEvent[], order: string[]) => [...new Set(order)].filter((k) => evs.some((e) => e.kind === k));

/** A residual group as opened: a kind's no-key events, a refusal's, a split's. */
export const noKeyOf = (g: any, token: number): Opened => ({ what: "no_key", kind: g.kind, in: [g.kind], was: g.count, token });
export const refusedOf = (g: any, token: number): Opened =>
  ({ what: "refused", field: g.field, value: g.value, why: g.why, in: kindsOf(g.samples || [], g.kinds || []), was: g.count, token });
export const splitOf = (g: any, token: number): Opened =>
  ({ what: "split", kinds: g.kinds, in: kindsOf(g.events || [], [...g.kinds, ...(g.main || [])]), was: g.objects, token });

/** The first group of a part of the residual (for the line above the steps). */
export function openFirst(r: any, what: "no_key" | "refused" | "split", token: number): Opened | null {
  const s = r?.residual;
  const g = what === "no_key" ? s?.no_key?.groups?.[0] : what === "refused" ? s?.refused?.groups?.[0] : s?.splits?.groups?.[0];
  return !g ? null : what === "no_key" ? noKeyOf(g, token) : what === "refused" ? refusedOf(g, token) : splitOf(g, token);
}

/** The banner over a kind's samples while a group is open in it. */
export function Banner({ o, live, kind, onUsual }: { o: Opened; live: Live | null; kind: string; onUsual: () => void }) {
  if (!live) {
    const was = o.what === "no_key" ? `${n(o.was)} events with no key` : o.what === "refused" ? `${n(o.was)} refused` : `${n(o.was)} possible splits`;
    return (
      <p className="wb-open wb-open-fixed" role="status" data-testid={`opened-${kind}`}>
        <strong>✓ fixed</strong> <span className="muted small">({was} before)</span>{" "}
        <button type="button" className="ghost small" aria-label="Close" onClick={onUsual}>×</button>
      </p>
    );
  }
  const shown = live.events.filter((e) => e.kind === kind).length;
  let what;
  if (o.what === "no_key") {
    const parts = [...live.untold.map((f) => `${f} is not told`), ...live.key.filter((f) => !live.untold.includes(f)).map((f) => `${f} reads no value`)];
    what = <>{shown} of {n(live.count)} events with no key{parts.length ? <> — {parts.join(", ")}</> : null}</>;
  } else if (o.what === "refused") {
    what = <>{shown} of {n(live.count)} refused events — {short(live.why, 140)}</>;
  } else {
    what = <>{shown} event{shown === 1 ? "" : "s"} of {live.objects?.map((x, i) => <span key={x}>{i > 0 && " and "}<code>{x}</code></span>)} — {n(live.count)} possible
      split{live.count === 1 ? "" : "s"}{live.key.length ? <>, the key&apos;s {live.key.join(", ")} read differently</> : null}</>;
  }
  return (
    <p className="wb-open" role="status" data-testid={`opened-${kind}`}>
      Showing <span data-testid={`opened-what-${kind}`}>{what}</span> · <button type="button" className="ghost small" onClick={onUsual}>show its usual samples</button>
    </p>
  );
}
