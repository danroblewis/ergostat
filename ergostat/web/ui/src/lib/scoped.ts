import type { RouteTable } from "./systemRoutes";

/* What a system's dashboards show (SPEC §4f, Dashboards per system): the projections, goals and agents the system
   contains (spec/scope.py, carried in the route table), and of them the ancillary ones (contained, not defined there),
   drawn greyer with a title saying where each is defined. A panel with a `system` parameter is scoped so; one without
   shows every one. */

export type Plural = "projections" | "goals" | "agents";

export type Scoped = {
  system: string;
  /** whether the system contains it */
  has: (kind: Plural, name: string) => boolean;
  /** where it is defined, when that is not this system (it is ancillary here); null when it is the system's own */
  ancillary: (kind: Plural, name: string) => string | null;
};

const where = (s: string | null) => (s === null ? "ergostat's own" : `defined in ${s === "" ? "the top level" : s}`);

/** A panel's system as a filter, or null (no `system`: every one). */
export function scopedBy(t: RouteTable | null | undefined, system: unknown): Scoped | null {
  if (typeof system !== "string" || system.startsWith("$") || !t || !(system in t.scopes)) return null;
  const of = (kind: Plural, name: string) => t[kind]?.[name];
  return {
    system,
    has: (kind, name) => !!of(kind, name)?.in.includes(system),
    ancillary: (kind, name) => {
      const x = of(kind, name);
      return !x || x.defined_in === system ? null : where(x.defined_in);
    },
  };
}

/** The class and title of a row or card that is ancillary in its system (nothing for its own). */
export function ancillaryMark(s: Scoped | null, kind: Plural, name: string): { className?: string; title?: string } {
  const why = s?.ancillary(kind, name);
  return why ? { className: "ancillary", title: why } : {};
}
