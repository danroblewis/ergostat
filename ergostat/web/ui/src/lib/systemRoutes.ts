/* The page's addresses per system (SPEC §4f, Addresses): the same rules as ergostat/spec/routes.py (its docstring says
   them), over the route table it writes (GET /api/route-table). Both are checked against tests/fixtures/route_cases.json
   (tests/test_system_routes.py runs this file with node). Self-contained, with no imports and only erasable types, so
   node runs it as it is. The page's resolver (Resolve.tsx) and every link it writes (lib/hrefs.ts) are these. */

export type Segment = { kind: "dashboard" | "projection" | "system"; name: string; default?: boolean; projection?: string };
/** A scope: its segment under its parent (`name`), its path, the names read in it (a name goes to one thing, by the
 *  fixed order: routes.py), and the goals and agents under its goals/ and agents/ by their names there. */
export type Scope = { within: string | null; name: string; path: string; segments: Record<string, Segment>;
  goals: Record<string, string>; agents: Record<string, string> };
/** `in`: the scopes that contain it; `at`: those where it holds its name, and that name (a remote's or a template's
 *  part is named by its short name inside its own system). */
export type Thing = { defined_in: string | null; in: string[]; at: Record<string, string>; id?: string; open?: boolean };
export type RouteTable = {
  reserved: string[];
  defaults: string[];
  scopes: Record<string, Scope>;
  projections: Record<string, Thing & { id: string }>;
  goals: Record<string, Thing>;
  agents: Record<string, Thing>;
  dashboards: Record<string, string>;
  shadowed: { scope: string; segment: string; kept: { kind: string; name: string }; lost: { kind: string; name: string };
    at: string | null; message: string }[];
  unaddressed: { kind: string; name: string; message: string }[];
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

/** The highest scope on s's chain that the thing is at. */
function top(t: RouteTable, thing: Thing, s: string | null): string | null {
  if (s === null) return null;
  const on = chain(t, s).filter((x) => x in thing.at);
  return on.length ? on[on.length - 1] : null;
}

function canonical(t: RouteTable, thing: Thing): string | null {
  const at = Object.keys(thing.at);
  if (!at.length) return null;
  if (thing.defined_in !== null) {
    const got = top(t, thing, thing.defined_in);
    if (got !== null) return got;
  }
  let best = at[0];
  for (const x of at) if (chain(t, x).length < chain(t, best).length) best = x;
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

/** What a projection's items' ids start with, left out of their addresses: none of an open one's (routes.py _prefix_of). */
const prefixOfThing = (thing: Thing): string | null => (thing.open ? "" : prefixOf(thing.id!));

function at(t: RouteTable, s: string, rest = ""): string {
  const base = t.scopes[s].path.replace(/\/$/, "");
  return rest ? `${base}/${rest}` : base || "/";
}

function table(t: RouteTable, kind: string): Record<string, Thing> {
  return kind === "projection" || kind === "item" ? t.projections : kind === "goal" ? t.goals : t.agents;
}

function addr(t: RouteTable, kind: string, name: string, s: string, id?: string): string {
  const seg = table(t, kind)[name].at[s] ?? name;
  if (kind === "projection") return at(t, s, enc(seg));
  if (kind === "item") {
    const p = prefixOfThing(t.projections[name]);
    const rest = p !== null && id!.startsWith(p) ? id!.slice(p.length) : id!;
    return at(t, s, `${enc(seg)}/${segs(rest)}`);
  }
  return at(t, s, `${kind === "goal" ? "goals" : "agents"}/${enc(seg)}`);
}

/** A projection's, goal's or agent's name in a scope (its short name inside the remote or template instance that made
 *  it), else its own: for the nav bar's and a dashboard's words. */
export function nameAt(t: RouteTable | null | undefined, kind: "projections" | "goals" | "agents", name: string,
                       scope: string | null | undefined): string {
  return (t && scope !== null && scope !== undefined && t[kind]?.[name]?.at?.[scope]) || name;
}

function thingAt(t: RouteTable, s: string, kind: "projection" | "item" | "goal" | "agent", name: string,
                 rest?: string): Resolved | null {
  const thing = table(t, kind)[name];
  if (!thing || !(s in thing.at)) return null;
  const out: Resolved = { scope: s, kind, name };
  if (kind === "item") {
    const p = prefixOfThing(thing);
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
      if (show && rest.length === 1 && (e.default || e.name === parts[i] || e.name.endsWith("." + parts[i]))) {
        const got = t.scopes[s][parts[i] as "goals" | "agents"]?.[rest[0]];
        return got !== undefined ? thingAt(t, s, show, got) : null;
      }
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
