/* a large view's line groups, parted (avoidSpec, avoid.js): libavoid weighs a crossing only between lines of one
   group, and that weighing is most of the routing's time, growing fast with a group's size. So a group of more than
   GROUP_CAP lines (an open system's own lines, or "", which holds every line of a view of one system) is parted, in
   name order:
     a. a hub (a part with more than HUB of the group's lines): every line at it goes to the shared group "";
     b. a line with an end that has no position goes to "" (the worst case: it never decides a band);
     c. the rest in components (lines joined where they share an end part);
     d. a component of more than GROUP_CAP lines cut into bands along its wider axis (x when its parts span at least as
        wide as tall, a zero span included; else y): parts by (that coordinate, id), each joining the band unless its
        lines to the band's parts would take the band past GROUP_CAP; a line with its ends in two bands goes to "";
     e. the pieces (components and bands), by (smallest x, smallest y, smallest line id), packed in that order into
        groups `${G}#k`, each taking pieces while it stays within GROUP_CAP.
   "" is parted too, first (in a view of one system every line is in it: its parts are in no open system), with one
   rule more: a line of "" at a part that has a line of another group (as given) stays in "", so that (ii) holds; its
   pieces go to groups `#k`. What the other groups set aside after it stays in "". No net rule runs here: nothing goes
   to "" for a net, so nothing cascades.
   What it guarantees:
     (i)   every group but "" has at most GROUP_CAP lines;
     (ii)  two lines that share an end part and are both outside "" are in one group, when that held of the grouping
           given (it does of avoidSpec's: a line is in a system's group only with both ends in that system): a net is
           split only between "" and one other group, at a hub, a band's edge, or a part with lines of two groups;
     (iii) a group of n lines is parted into at most 2·⌈n / GROUP_CAP⌉ + 1 groups ("" counted): packing is consecutive,
           so two neighbouring groups together hold more than GROUP_CAP (each is a router holding every shape);
     (iv)  a group of at most GROUP_CAP lines is returned unchanged: a view whose groups all are is grouped as before.
   "" is not bounded by the parting: hubs, band edges (one line per cut in a chain, more where a component has
   long lines) and lines at the parts of systems' groups all go to it. Past SHARED_CAP lines it is routed free (free: true; avoidSpec
   gives it no weight on crossings). The result depends only on the inputs as sets */
const GROUP_CAP = 100, SHARED_CAP = 100, HUB = 8;

function partGroups(conns, at, groups) {
  const byId = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const sorted = [...conns].sort((a, b) => byId(a.id, b.id));
  const out = Object.fromEntries(sorted.map((c) => [c.id, groups[c.id] ?? ""]));
  const of = {};
  for (const c of sorted) (of[out[c.id]] ||= []).push(c);
  const has = (p) => Object.prototype.hasOwnProperty.call(at, p);
  const others = new Set(sorted.filter((c) => out[c.id]).flatMap((c) => [c.s, c.t]));   // parts with a line of a group
  for (const G of Object.keys(of).filter((g) => of[g].length > GROUP_CAP).sort(byId)) {
    const list = of[G], degree = {};
    for (const c of list) for (const p of new Set([c.s, c.t])) degree[p] = (degree[p] || 0) + 1;
    // a, b: a hub's lines, and a line with an end nowhere, to ""; and parting "", a line at another group's part
    const rest = [];
    for (const c of list) {
      if (degree[c.s] > HUB || degree[c.t] > HUB || !has(c.s) || !has(c.t) || (!G && (others.has(c.s) || others.has(c.t)))) out[c.id] = "";
      else rest.push(c);
    }
    // c: components, by a union of their end parts
    const up = {};
    const root = (p) => { while (up[p] !== p) p = up[p] = up[up[p]]; return p; };
    for (const c of rest) { up[c.s] ??= c.s; up[c.t] ??= c.t; }
    for (const c of rest) { const a = root(c.s), b = root(c.t); if (a !== b) up[a > b ? a : b] = a > b ? b : a; }
    const comps = {};
    for (const c of rest) (comps[root(c.s)] ||= []).push(c);
    // d: a component past the cap, in bands
    const pieces = [];
    for (const comp of Object.values(comps)) {
      if (comp.length <= GROUP_CAP) { pieces.push(comp); continue; }
      const parts = [...new Set(comp.flatMap((c) => [c.s, c.t]))].sort(byId);
      const span = (k) => Math.max(...parts.map((p) => at[p][k])) - Math.min(...parts.map((p) => at[p][k]));
      const k = span(0) >= span(1) ? 0 : 1;
      parts.sort((p, q) => at[p][k] - at[q][k] || byId(p, q));
      const lines = {};
      for (const c of comp) for (const p of new Set([c.s, c.t])) (lines[p] ||= []).push(c);
      const band = {};
      let n = -1, size = 0;
      for (const p of parts) {
        const add = lines[p].filter((c) => c.s === c.t || band[c.s === p ? c.t : c.s] === n).length;
        if (n < 0 || (size + add > GROUP_CAP && size > 0)) {
          n += 1;
          size = lines[p].filter((c) => c.s === c.t).length;
        } else size += add;
        band[p] = n;
      }
      const bands = [];
      for (const c of comp) {
        if (band[c.s] === band[c.t]) (bands[band[c.s]] ||= []).push(c);
        else out[c.id] = "";
      }
      pieces.push(...bands.filter(Boolean));
    }
    // e: the pieces packed in order, each group within the cap
    const key = (piece) => {
      const ps = piece.flatMap((c) => [c.s, c.t]);
      return [Math.min(...ps.map((p) => at[p][0])), Math.min(...ps.map((p) => at[p][1])), piece[0].id];
    };
    const keyed = pieces.map((piece) => [key(piece), piece]);
    keyed.sort(([a], [b]) => a[0] - b[0] || a[1] - b[1] || byId(a[2], b[2]));
    let k = 0, total = 0;
    for (const [, piece] of keyed) {
      if (total && total + piece.length > GROUP_CAP) { k += 1; total = 0; }
      total += piece.length;
      for (const c of piece) out[c.id] = `${G}#${k}`;
    }
  }
  const shared = Object.values(out).filter((g) => g === "").length;
  return { groups: out, free: shared > SHARED_CAP };
}
