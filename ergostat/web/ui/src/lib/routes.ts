/* The page's addresses are the model's (SPEC §4f): /api, /static and /remote are the server's; every other path is
   resolved here, in this order:
     1. a dashboard the model declares, at /NAME (named as a kind: that kind's page, its $kind the kind);
     2. a kind of item, at /KIND (its list) and /KIND/REST (one of its items: REST is what its id glob's * matched,
        ticket/1 at /ticket/1; a kind whose glob is not PREFIX* writes the whole id);
     3. ergostat's own pages, each a dashboard of its own (lib/pages.ts) at its name: /diagram, /dashboard, /goals,
        /agents, /record, /agent/NAME and /item/ID (any id, a kind's or not).
   ?builtin=1 shows ergostat's own page for an address whatever the model names there. The kinds are set once the
   page has asked (/api/routes, state/dashboards.tsx); until then an item's link is /item/ID, which leads to the same. */

export type KindRoute = { name: string; id: string; declared?: boolean };

export const BUILTIN = ["diagram", "dashboard", "goals", "agents", "agent", "record", "item"] as const;

let kinds: KindRoute[] = [];
const globs = new Map<string, RegExp>();

/** The kinds of item, in the model's order (the first whose glob matches an id is its kind). */
export function setKinds(k: KindRoute[]): void {
  kinds = k;
}
export const knownKinds = () => kinds;

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

export const kindOfId = (id: string) => kinds.find((k) => globRe(k.id).test(id));
export const isKind = (name: string) => kinds.some((k) => k.name === name);

const segs = (s: string) => s.split("/").map(encodeURIComponent).join("/");

/** An item's own address, /KIND/REST; null when no kind is known to match it (then /item/ID). */
export function itemPath(id: string): string | null {
  const k = kindOfId(id);
  if (!k) return null;
  const p = prefixOf(k.id);
  const rest = p != null && id.startsWith(p) ? id.slice(p.length) : id;
  return rest ? `/${encodeURIComponent(k.name)}/${segs(rest)}` : null;
}

/** The id an address under a kind names: its glob's prefix and REST (or REST, the whole id). */
export function idOf(kind: string, rest: string): string {
  const k = kinds.find((x) => x.name === kind);
  const p = k ? prefixOf(k.id) : null;
  return p != null ? p + rest : rest;
}
