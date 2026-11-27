/* The page's addresses per system (SPEC §4f, Addresses): the same rules as ergostat/spec/routes.py (its docstring says
   them), over the route table it writes (GET /api/route-table). Both are checked against tests/fixtures/route_cases.json
   (tests/test_system_routes.py runs this file with node). Self-contained, with no imports and only erasable types, so
   node runs it as it is. Not yet the page's resolver: lib/routes.ts and Resolve.tsx still are. */

export type Segment = { kind: "dashboard" | "projection" | "system"; name: string; default?: boolean; projection?: string };
export type Scope = { within: string | null; path: string; segments: Record<string, Segment> };
export type Thing = { defined_in: string | null; in: string[]; id?: string };
export type RouteTable = {
  reserved: string[];
  defaults: string[];
  scopes: Record<string, Scope>;
  projections: Record<string, Thing & { id: string }>;
  goals: Record<string, Thing>;
  agents: Record<string, Thing>;
  dashboards: Record<string, string>;
  collisions: { scope: string; segment: string; things: { kind: string; name: string }[]; message: string }[];
};
export type Resolved = {
  scope: string;
  kind: "dashboard" | "projection" | "item" | "goal" | "agent" | "system";
  name: string;
  id?: string;
  projection?: string;
  redirect?: string;
};
export type Named =
  | { kind: "projection" | "goal" | "agent" | "dashboard" | "system"; name: string }
  | { kind: "item"; id: string; projection?: string };

const TOP = "";
const SHOWS: Record<string, "goal" | "agent"> = { goals: "goal", agents: "agent" };

/** encodeURIComponent: Python's quote(s, safe="!*'()") writes the same. */
const enc = (s: string) => encodeURIComponent(s);
const segs = (s: string) => s.split("/").map(enc).join("/");

function chain(t: RouteTable, s: string | null): string[] {
  const out: string[] = [];
  while (s !== null && s !== undefined && !out.includes(s)) {
    out.push(s);
    s = t.scopes[s]?.within ?? null;
  }
  return out;
}

/** The highest scope on s's chain that contains the thing. */
function top(t: RouteTable, thing: Thing, s: string | null): string | null {
  if (s === null) return null;
  const on = chain(t, s).filter((x) => thing.in.includes(x));
  return on.length ? on[on.length - 1] : null;
}

function canonical(t: RouteTable, thing: Thing): string | null {
  if (!thing.in.length) return null;
  if (thing.defined_in !== null) {
    const got = top(t, thing, thing.defined_in);
    if (got !== null) return got;
  }
  let best = thing.in[0];
  for (const x of thing.in) if (chain(t, x).length < chain(t, best).length) best = x;
  return best;
}

const globs = new Map<string, RegExp>();
function globRe(g: string): RegExp {
  let re = globs.get(g);
  if (re) return re;
  let out = "";
  for (let i = 0; i < g.length; i++) {
    const ch = g[i];
    if (ch === "*") out += ".*";
    else if (ch === "?") out += ".";
    else if (ch === "[" && g.indexOf("]", i + 2) >= 0) {
      const j = g.indexOf("]", i + 2);
      let set = g.slice(i + 1, j);
      if (set[0] === "!") set = "^" + set.slice(1);
      out += `[${set.replace(/\\/g, "\\\\")}]`;
      i = j;
    } else out += ch.replace(/[.*+?^${}()|[\]\\/-]/g, "\\$&");
  }
  re = new RegExp(`^${out}$`, "s");
  globs.set(g, re);
  return re;
}

function prefixOf(glob: string): string | null {
  if (!glob.endsWith("*")) return null;
  const p = glob.slice(0, -1);
  return /[*?[]/.test(p) ? null : p;
}

function at(t: RouteTable, s: string, rest = ""): string {
  const base = t.scopes[s].path.replace(/\/$/, "");
  return rest ? `${base}/${rest}` : base || "/";
}

function addr(t: RouteTable, kind: string, name: string, s: string, id?: string): string {
  if (kind === "projection") return at(t, s, enc(name));
  if (kind === "item") {
    const p = prefixOf(t.projections[name].id);
    const rest = p !== null && id!.startsWith(p) ? id!.slice(p.length) : id!;
    return at(t, s, `${enc(name)}/${segs(rest)}`);
  }
  return at(t, s, `${kind === "goal" ? "goals" : "agents"}/${enc(name)}`);
}

function table(t: RouteTable, kind: string): Record<string, Thing> {
  return kind === "projection" || kind === "item" ? t.projections : kind === "goal" ? t.goals : t.agents;
}

function thingAt(t: RouteTable, s: string, kind: "projection" | "item" | "goal" | "agent", name: string,
                 rest?: string): Resolved | null {
  const thing = table(t, kind)[name];
  if (!thing || !thing.in.includes(s)) return null;
  const out: Resolved = { scope: s, kind, name };
  if (kind === "item") {
    const p = prefixOf(thing.id!);
    out.id = p !== null ? p + rest : rest;
  }
  const up = top(t, thing, s);
  if (up !== null && up !== s) out.redirect = addr(t, kind, name, up, out.id);
  return out;
}

/** What an address names, or null (nothing there, or the server's own): routes.py resolve. */
export function resolve(t: RouteTable, path: string): Resolved | null {
  path = path.split("?")[0].split("#")[0];
  const trimmed = path.replace(/^\/+|\/+$/g, "");
  let parts: string[];
  try {
    parts = trimmed ? trimmed.split("/").map((x) => decodeURIComponent(x)) : [];
  } catch {
    return null;                                     // a malformed %: no address
  }
  if (parts.length && t.reserved.includes(parts[0])) return null;
  let s = TOP;
  for (let i = 0; i < parts.length; ) {
    const e = t.scopes[s].segments[parts[i]];
    if (!e) return null;
    const rest = parts.slice(i + 1);
    if (e.kind === "system") {
      s = e.name;
      i += 1;
      continue;
    }
    if (e.kind === "dashboard") {
      if (!rest.length) return { scope: s, kind: "dashboard", name: e.name, ...(e.projection ? { projection: e.projection } : {}) };
      if (e.projection) return thingAt(t, s, "item", e.projection, rest.join("/"));
      const show = SHOWS[parts[i]];
      if (show && rest.length === 1 && (e.default || e.name === parts[i] || e.name.endsWith("." + parts[i])))
        return thingAt(t, s, show, rest[0]);
      return null;
    }
    return rest.length ? thingAt(t, s, "item", e.name, rest.join("/")) : thingAt(t, s, "projection", e.name);
  }
  return { scope: s, kind: "system", name: s };
}

/** The first projection, in the model's order, whose id glob matches the id. */
export function projectionOf(t: RouteTable, id: string): string | null {
  return Object.keys(t.projections).find((n) => globRe(t.projections[n].id).test(id)) ?? null;
}

/** A thing's address: routes.py href. */
export function href(t: RouteTable, thing: Named, scope?: string | null): string | null {
  if (thing.kind === "system") return t.scopes[thing.name]?.path ?? null;
  if (thing.kind === "dashboard") {
    const name = thing.name;
    if (name in t.dashboards) {
      const s = t.dashboards[name];
      const local = s && name.startsWith(s + ".") ? name.slice(s.length + 1) : name;
      return at(t, s, enc(local));
    }
    const s = scope ?? TOP;
    return t.defaults.includes(name) && s in t.scopes ? at(t, s, enc(name)) : null;
  }
  let name: string | null;
  let id: string | undefined;
  if (thing.kind === "item") {
    name = thing.projection ?? projectionOf(t, thing.id);
    id = thing.id;
  } else name = thing.name;
  if (name === null) return null;
  const got = table(t, thing.kind)[name];
  if (!got) return null;
  let s = scope !== undefined && scope !== null ? top(t, got, scope) : null;
  if (s === null) s = canonical(t, got);
  return s === null ? null : addr(t, thing.kind, name, s, id);
}
