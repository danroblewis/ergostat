/* The model's projections and their id globs (GET /api/routes, set by state/dashboards.tsx): which projections see an
   id, and the id an address under a projection names. The addresses themselves are lib/systemRoutes.ts's (SPEC §4f,
   Addresses), read over GET /api/route-table; until that table is here, an item's link is /item/ID or /PROJECTION/REST,
   which the page leads to the same place (Resolve.tsx). */

export type ProjectionRoute = { name: string; id: string; declared?: boolean; group?: string | null; system?: string };

let projections: ProjectionRoute[] = [];
const globs = new Map<string, RegExp>();

/** The model's projections, in its order. */
export function setProjections(p: ProjectionRoute[]): void {
  projections = p;
}
export const knownProjections = () => projections;

/** fnmatch's glob as a RegExp: `*` anything (a / too), `?` one character, `[...]` one of them. */
function globRe(g: string): RegExp {
  let re = globs.get(g);
  if (re) return re;
  let out = "";
  for (let i = 0; i < g.length; i++) {
    const ch = g[i];
    if (ch === "*") out += ".*";
    else if (ch === "?") out += ".";
    else if (ch === "[") {
      const j = g.indexOf("]", i + 2);
      if (j < 0) out += "\\[";
      else { let set = g.slice(i + 1, j); if (set[0] === "!") set = "^" + set.slice(1); out += `[${set.replace(/\\/g, "\\\\")}]`; i = j; }
    } else out += ch.replace(/[.+^${}()|\\/]/g, "\\$&");
  }
  re = new RegExp(`^${out}$`, "s");
  globs.set(g, re);
  return re;
}

/** The fixed part of a glob of the form PREFIX* (ticket/*), else null (the whole id is written). */
function prefixOf(glob: string): string | null {
  if (!glob.endsWith("*")) return null;
  const p = glob.slice(0, -1);
  return /[*?[]/.test(p) ? null : p;
}

/** Every projection whose glob matches an id: each folds its events into an item of its own. */
export const projectionsOfId = (id: string) => projections.filter((k) => globRe(k.id).test(id));
export const isProjection = (name: string) => projections.some((k) => k.name === name);

/** An id written into an address: each part between its slashes encoded, the slashes kept (ticket/12, not ticket%2F12). */
export const segs = (s: string) => s.split("/").map(encodeURIComponent).join("/");

/** An item's own address, /PROJECTION/REST: projection's item of the id (with none named, the one projection that
 *  matches it); null when it is not known to match, or several do and none is named (then /item/ID, which lists them). */
export function itemPath(id: string, projection?: string | null): string | null {
  const ks = projectionsOfId(id);
  const k = projection ? ks.find((x) => x.name === projection) : ks.length === 1 ? ks[0] : undefined;
  if (!k) return null;
  const p = prefixOf(k.id);
  const rest = p != null && id.startsWith(p) ? id.slice(p.length) : id;
  return rest ? `/${encodeURIComponent(k.name)}/${segs(rest)}` : null;
}

/** The id an address under a projection names: its glob's prefix and REST (or REST, the whole id). */
export function idOf(projection: string, rest: string): string {
  const k = projections.find((x) => x.name === projection);
  const p = k ? prefixOf(k.id) : null;
  return p != null ? p + rest : rest;
}
