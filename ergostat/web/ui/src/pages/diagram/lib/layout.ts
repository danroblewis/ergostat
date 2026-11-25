/* The three views' layouts, with ELK (layered): plain TypeScript, no DOM. What React draws is what these return:
   { children: [{id, x, y, width, height, labels}], edges: [{id, sections}], width, height, hulls }.
   Ported in spirit from layouts.js, dynamics.js (sizes), blocks.js (bdSize) and process.js (pmLayoutKind); not the
   old page's anchors, satellites, wrapping or libavoid routing (see the README in this folder). */
// @ts-ignore: the bundled build has the API's types
import ELK from "elkjs/lib/elk.bundled.js";
import { textWidth, wrapWords, CH } from "./geom";

const elk = new (ELK as any)();

export interface Placed { id: string; x: number; y: number; width: number; height: number; labels?: any[]; ports?: any[] }
export interface Layout { children: Placed[]; edges: any[]; width: number; height: number; hulls: Hull[] }
export interface Hull { name: string; x: number; y: number; width: number; height: number }

const TIGHT = {
  "elk.layered.spacing.nodeNodeBetweenLayers": "56", "elk.spacing.nodeNode": "28", "elk.spacing.edgeNode": "14",
  "elk.spacing.componentComponent": "40",
};
const BASE = {
  "elk.algorithm": "layered", "elk.direction": "RIGHT", "elk.edgeRouting": "ORTHOGONAL",
  "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX", "elk.portConstraints": "FIXED_SIDE", ...TIGHT,
};

/* ---- the Dynamics view's parts (dynamics.js: sdSize, systemSize) */
export const SYS_TOP = 70, SYS_ROW = 20;
export const UPKEEP = "ergostat's upkeep of this model, not the system";
export const nameOf = (n: any): string => n?.short || n?.label || "";

export function sdValue(n: any): string {
  if (n.role === "desired" || n.role === "gap") return n.valueText || "–";
  if (n.bare || n.role === "decision") return "";
  const v = n.valueText && n.valueText !== "?" ? n.valueText : "–";
  return n.unit ? `${v} ${n.unit}` : v;
}
export const sdNoUnit = (n: any) => n.kind === "stock" && !n.bare && !(n.unit || "").trim();
export function sdAuxLines(n: any): string[] {
  if (n.role === "decision") return [nameOf(n)];
  return [nameOf(n), sdValue(n), n.exogenous ? "(exogenous)" : null, n.noFeedback ? "→ no feedback" : null].filter(Boolean) as string[];
}
export function sdLabelLines(n: any): string[] {
  if (n.kind === "valve" || n.kind === "disturbance") return n.bare ? [nameOf(n)] : [nameOf(n), n.rate == null ? "not measured" : n.rateText];
  if (n.kind === "cloud" && n.beyond) return [`<${n.beyond}>`];
  if (n.kind === "cloud" && n.from) return [`from ${n.from}`];
  return [];
}
export const portSide = (p: any): "west" | "east" => p.at || (p.side === "in" ? "west" : "east");
export function systemSize(n: any): [number, number] {
  const ports = n.ports || [];
  const side = (d: string) => ports.filter((p: any) => portSide(p) === d);
  const lw = (ps: any[]) => Math.max(0, ...ps.map((p) => textWidth(p.label + (p.value ? "  " + p.value : ""))));
  const w = Math.max(240, textWidth(n.label) * 1.25 + 150, lw(side("west")) + lw(side("east")) + 60,
    n.remote ? textWidth(n.remote.says) + 40 : 0, n.upkeep ? textWidth(UPKEEP) + 40 : 0);
  return [w, Math.max(96, SYS_TOP + Math.max(side("west").length, side("east").length) * SYS_ROW + 6 + (n.inner?.length ? 16 : 0))];
}
export function sdSize(n: any): [number, number] {
  if (n.kind === "stock") return [Math.max(96, textWidth(nameOf(n)) * 1.05 + 28, textWidth(sdValue(n) + (sdNoUnit(n) ? " unit ?" : "")) + 28), 44];
  if (n.kind === "auxiliary") {
    const lines = sdAuxLines(n);
    return [Math.max(...lines.map((t, i) => textWidth(t) * (i === 0 ? 1.02 : 0.92))) + 10, 6 + lines.length * 14];
  }
  if (n.kind === "system") return systemSize(n);
  if (n.kind === "terminal") return [textWidth(n.label) + 16, 22];
  if (n.kind === "cloud") return [46, 30];
  return [40, 40];
}
export const systemDescLines = (n: any, w: number) =>
  n.remote ? [n.remote.says] : wrapWords(n.description || "a module: open it to see its structure", Math.floor((w - 32) / CH), 2);

function hullsOf(g: any, children: Placed[]): Hull[] {
  const open: string[] = g.open || [];
  const byId = Object.fromEntries(g.nodes.map((n: any) => [n.id, n]));
  const out: Hull[] = [];
  for (const name of open) {
    const mine = children.filter((c) => (byId[c.id]?.systems || []).includes(name));
    if (!mine.length) continue;
    const pad = 16;
    const x0 = Math.min(...mine.map((c) => c.x)) - pad, y0 = Math.min(...mine.map((c) => c.y)) - pad - 14;
    const x1 = Math.max(...mine.map((c) => c.x + c.width)) + pad, y1 = Math.max(...mine.map((c) => c.y + c.height + (c.labels?.length ? 30 : 0))) + pad;
    out.push({ name, x: x0, y: y0, width: x1 - x0, height: y1 - y0 });
  }
  return out;
}

async function run(graph: any, g: any): Promise<Layout> {
  const lay = await elk.layout(graph);
  const flat: Placed[] = [];
  const edges: any[] = [...(lay.edges || [])];
  const walk = (node: any, ox: number, oy: number) => {
    for (const c of node.children || []) {
      if (c.children?.length) {
        walk(c, ox + c.x, oy + c.y);
        for (const e of c.edges || []) edges.push(shift(e, ox + c.x, oy + c.y));
        flat.push({ id: c.id, x: ox + c.x, y: oy + c.y, width: c.width, height: c.height, labels: c.labels, ports: c.ports, ...{ frame: true } } as any);
      } else flat.push({ ...c, x: ox + c.x, y: oy + c.y });
    }
  };
  walk(lay, 0, 0);
  const children = flat.filter((c: any) => !c.frame);
  const frames = flat.filter((c: any) => c.frame).map((c) => ({ name: c.id.replace(/^(kind|open):/, ""), x: c.x, y: c.y, width: c.width, height: c.height }));
  return { children, edges, width: lay.width, height: lay.height, hulls: frames.length ? frames : hullsOf(g, children) };
}
function shift(e: any, dx: number, dy: number) {
  const p = (q: any) => ({ x: q.x + dx, y: q.y + dy });
  return { ...e, sections: (e.sections || []).map((s: any) => ({ ...s, startPoint: p(s.startPoint), endPoint: p(s.endPoint), bendPoints: (s.bendPoints || []).map(p) })),
           labels: (e.labels || []).map((l: any) => ({ ...l, x: l.x + dx, y: l.y + dy })) };
}

export async function layoutDynamics(g: any): Promise<Layout> {
  const ids = new Set(g.nodes.map((n: any) => n.id));
  const children = g.nodes.map((n: any) => {
    const [w, h] = sdSize(n);
    const lines = sdLabelLines(n);
    const node: any = { id: n.id, width: w, height: h, layoutOptions: { "elk.portConstraints": "FIXED_SIDE" } };
    if (lines.length) node.labels = [{ text: lines.join("\n"), width: Math.max(...lines.map(textWidth)) + 4, height: lines.length * 16,
      layoutOptions: { "elk.nodeLabels.placement": "OUTSIDE V_BOTTOM H_CENTER" } }];
    if (n.kind === "system") {
      const at = { west: 0, east: 0 };
      node.ports = (n.ports || []).map((p: any) => {
        const side = portSide(p);
        const y = SYS_TOP + at[side]++ * SYS_ROW;
        return { id: p.id, width: 1, height: 1, x: side === "west" ? 0 : w - 1, y, layoutOptions: { "elk.port.side": side === "west" ? "WEST" : "EAST" } };
      });
      node.layoutOptions["elk.portConstraints"] = "FIXED_POS";
    }
    return node;
  });
  const edges = g.edges.filter((e: any) => ids.has(e.source) && ids.has(e.target)).map((e: any) => ({
    id: e.id, sources: [e.sourcePort || e.source], targets: [e.targetPort || e.target],
    ...(e.kind === "connector" ? { layoutOptions: { "elk.layered.priority.direction": "0" } } : {}),
  }));
  const open: string[] = g.open || [];
  if (!open.length) return run({ id: "root", layoutOptions: { ...BASE, "elk.edgeRouting": "POLYLINE", "elk.portConstraints": "UNDEFINED" }, children, edges }, g);
  // each open system laid out in its own box (layouts.js's "separate"), so no two outlines overlap
  const groupOf: Record<string, string> = {};
  for (const n of g.nodes) {
    const mine = (n.systems || []).filter((x: string) => open.includes(x));
    if (mine.length) groupOf[n.id] = mine[mine.length - 1];
  }
  const groups = [...new Set(Object.values(groupOf))];
  const inner = { ...BASE, "elk.edgeRouting": "POLYLINE", "elk.portConstraints": "UNDEFINED", "elk.padding": "[top=30,left=16,bottom=16,right=16]" };
  const nodeById = Object.fromEntries(children.map((c: any) => [c.id, c]));
  const ownerOf = (end: string) => groupOf[end] || groupOf[g.edges.find((e: any) => e.sourcePort === end || e.targetPort === end)?.[g.edges.find((e: any) => e.sourcePort === end) ? "source" : "target"]];
  const rootEdges: any[] = [], groupEdges: Record<string, any[]> = {};
  for (const e of edges) {
    const a = ownerOf(e.sources[0]), b = ownerOf(e.targets[0]);
    if (a && a === b) (groupEdges[a] ||= []).push(e); else rootEdges.push(e);
  }
  const top = [
    ...children.filter((c: any) => !groupOf[c.id]),
    ...groups.map((name) => ({ id: "open:" + name, layoutOptions: inner, children: g.nodes.filter((n: any) => groupOf[n.id] === name).map((n: any) => nodeById[n.id]),
      edges: groupEdges[name] || [] })),
  ];
  return run({ id: "root", layoutOptions: { ...BASE, "elk.edgeRouting": "POLYLINE", "elk.portConstraints": "UNDEFINED", "elk.hierarchyHandling": "INCLUDE_CHILDREN" },
    children: top, edges: rootEdges }, g);
}

/* ---- the Blocks view (blocks.js: bdSize, simplified: no fractions measured in their own font) */
const BD = { SUM: 24, PORT: 18, TIER: 12 };
export const BD_TIER: Record<string, string> = { person: "person", ai: "AI agent", "narrow-ai": "narrow AI", decision: "decision", program: "program", rule: "rule" };
export const symText = (fn: any) => `${fn?.sym || ""}${fn?.sub || ""}${fn?.arg ? `(${fn.arg})` : ""}`;
export function bdCaption(n: any): string {
  const fn = n.fn || {}, tier = n.tier ? BD_TIER[n.tier] || n.tier : "";
  if (fn.name) return [n.label, fn.kind || tier].filter(Boolean).join(" · ");
  return tier;
}
export function bdSize(n: any): [number, number] {
  if (n.kind === "sum") return [BD.SUM, BD.SUM];
  const sideN = Math.max(n.ins?.length || 0, n.outs?.length || 0);
  if (n.kind === "mux" || n.kind === "demux") return [7, Math.max(34, (n.n || 2) * 18)];
  if (n.kind === "input" || n.kind === "output") return [Math.max(26, textWidth(symText(n.fn)) * 0.9 + 14), 22];
  if (n.kind === "port") return [Math.max(40, textWidth(symText(n.fn)) + 22), 22];
  if (n.kind === "sampler") return [36, 24];
  if (n.role === "sensor" || n.role === "collector") {
    const reads = [].concat(n.fn?.reads || []).map(String);
    return [Math.max(84, ...reads.map((r) => textWidth(r) * 0.9 + 20)), Math.max(28 + reads.length * 13, (sideN + 1) * BD.PORT)];
  }
  const fn = n.fn || {};
  let w = Math.max(84, textWidth(symText(fn)) + 28), h = 46;
  if (fn.name) w = Math.max(w, textWidth(fn.name) + 28);
  else if (fn.expr) { w = Math.max(w, textWidth(fn.expr) + 24); h = 54; }
  if (n.role === "subsystem") { w += 18; h = Math.max(h, 54); }
  if (n.upkeep) { w = Math.max(w, textWidth(UPKEEP) * 0.9 + 20); h += 16; }
  const cap = bdCaption(n);
  if (cap) w = Math.max(w, textWidth(cap) * 0.9 + 12);
  return [Math.round(w), Math.max(h, (sideN + 1) * BD.PORT) + (cap ? BD.TIER : 0)];
}
const SIDE: Record<string, string> = { W: "WEST", E: "EAST", N: "NORTH", S: "SOUTH" };

export async function layoutBlocks(g: any): Promise<Layout> {
  const ids = new Set(g.nodes.map((n: any) => n.id));
  const children = g.nodes.map((n: any) => {
    const [w, h] = bdSize(n);
    const ports = [...(n.ins || []), ...(n.outs || [])].map((p: any) => ({
      id: p.id, width: 1, height: 1, layoutOptions: { "elk.port.side": SIDE[p.side] || (n.ins?.includes(p) ? "WEST" : "EAST") },
    }));
    return { id: n.id, width: w, height: h, ports, layoutOptions: { "elk.portConstraints": "FIXED_SIDE" } };
  });
  const edges = g.edges.filter((e: any) => ids.has(e.source) && ids.has(e.target)).map((e: any) => ({
    id: e.id, sources: [e.sourcePort || e.source], targets: [e.targetPort || e.target],
  }));
  return run({ id: "root", layoutOptions: { ...BASE, "elk.layered.spacing.nodeNodeBetweenLayers": "64", "elk.spacing.nodeNode": "36" }, children, edges }, { ...g, open: [] });
}

/* ---- the Process view (process.js: each kind's map in its frame, activities left to right in time order) */
export const PM = { PAD: 22, TITLE: 26, H: 44, PILL: 28 };
export const pmNodeSub = (n: any) =>
  (n.now != null ? `now ${n.now} · ` : "") + `${n.count}×` + (n.items !== n.count ? ` · ${n.items} item${n.items === 1 ? "" : "s"}` : "");
export function pmNodeSize(n: any): [number, number] {
  if (n.kind !== "activity") return [Math.max(76, textWidth(`${n.label} ${n.count}`) + 40), PM.PILL];
  return [Math.round(Math.max(96, textWidth(n.label) * 1.08 + 28, textWidth(pmNodeSub(n)) * 0.95 + 24)), PM.H];
}
export async function layoutProcess(g: any, label: (e: any) => string): Promise<Layout> {
  const kinds: string[] = [...new Set<string>(g.nodes.map((n: any) => n.itemKind))];
  const kindOf = Object.fromEntries(g.nodes.map((n: any) => [n.id, n.itemKind]));
  const opts = {
    "elk.algorithm": "layered", "elk.direction": "RIGHT", "elk.edgeRouting": "ORTHOGONAL",
    "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES", "elk.layered.cycleBreaking.strategy": "MODEL_ORDER",
    "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX", "elk.layered.spacing.nodeNodeBetweenLayers": "56",
    "elk.spacing.nodeNode": "30", "elk.spacing.edgeNode": "16", "elk.edgeLabels.placement": "CENTER",
    "elk.padding": `[top=${PM.PAD + PM.TITLE},left=${PM.PAD},bottom=${PM.PAD},right=${PM.PAD}]`,
  };
  // each kind's map laid out alone, then stacked, one under another (process.js lays them out alone too)
  const out: Layout = { children: [], edges: [], width: 0, height: 0, hulls: [] };
  let y = 0;
  for (const k of kinds) {
    const graph = {
      id: "kind:" + k, layoutOptions: opts,
      children: g.nodes.filter((n: any) => n.itemKind === k).map((n: any) => { const [w, h] = pmNodeSize(n); return { id: n.id, width: w, height: h }; }),
      edges: g.edges.filter((e: any) => kindOf[e.source] === k && kindOf[e.target] === k).map((e: any) => {
        const t = label(e);
        return { id: e.id, sources: [e.source], targets: [e.target], labels: t ? [{ text: t, width: textWidth(t) + 8, height: 14 }] : [] };
      }),
    };
    const lay = await elk.layout(graph);
    for (const c of lay.children || []) out.children.push({ ...c, y: c.y + y });
    for (const e of lay.edges || []) out.edges.push(shift(e, 0, y));
    out.hulls.push({ name: k, x: 0, y, width: lay.width, height: lay.height });
    out.width = Math.max(out.width, lay.width);
    y += lay.height + 40;
  }
  out.height = y;
  return out;
}

/** What the layout depends on: a new answer whose structure is the same keeps its positions. */
export function structureKey(g: any): string {
  return JSON.stringify([g.kind, g.open, g.nodes.map((n: any) => [n.id, (n.ports || []).length, (n.ins || []).length, (n.outs || []).length, n.kind === "process" ? 0 : n.label]),
    g.edges.map((e: any) => e.id)]);
}
