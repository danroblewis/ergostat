import { arrowHead, edgePoints, midOf, roundedPath } from "./geom";
import { pmNodeSub, PM, type Layout } from "./layout";
import { dur } from "../../lib/format";
import type { Acts } from "./Dynamics";

/* The Process view: how items moved, from the record (process.js's pmNode, pmEdgeContent), each kind in its frame. */

export const pmLabel = (e: any, show: string) =>
  e.kind === "related" ? (show === "times" ? e.relation : `${e.relation} ${e.count}`)
    : show === "times" ? (e.median != null ? dur(e.median) : "") : String(e.count);

function PmNode({ n, w, h, most }: { n: any; w: number; h: number; most: number }) {
  if (n.kind !== "activity") {
    const cy = h / 2;
    return (
      <g>
        <rect className="hit" width={w} height={h} rx={h / 2} fill="var(--panel)" stroke="var(--ink)" strokeWidth={1.4} />
        {n.kind === "start" ? <path d={`M13,${cy - 5} L21,${cy} L13,${cy + 5} Z`} fill="var(--ink)" />
          : <rect x={12} y={cy - 4.5} width={9} height={9} fill="var(--ink)" />}
        <text x={28} y={cy + 4} className="t-label">{n.label}<tspan className="t-sub" dx={6}>{n.count}</tspan></text>
      </g>
    );
  }
  const f = most ? Math.sqrt(n.count / most) : 0;
  return (
    <g>
      <rect className="hit" width={w} height={h} rx={6} fill="var(--panel)" stroke="var(--ink)" strokeWidth={1.2} />
      <rect x={0.6} y={0.6} width={w - 1.2} height={h - 1.2} rx={5.5} fill="var(--ink)" opacity={(0.02 + 0.1 * f).toFixed(3)} pointerEvents="none" />
      <text x={w / 2} y={18} textAnchor="middle" className="t-label">{n.label}</text>
      <text x={w / 2} y={34} textAnchor="middle" className="t-sub">{pmNodeSub(n)}</text>
    </g>
  );
}

export function ProcessDrawing({ g, lay, acts, show }: { g: any; lay: Layout; acts: Acts; show: string }) {
  const byId: Record<string, any> = Object.fromEntries(g.nodes.map((n: any) => [n.id, n]));
  const edgeById: Record<string, any> = Object.fromEntries(g.edges.map((e: any) => [e.id, e]));
  const most = Math.max(0, ...g.nodes.map((n: any) => n.count || 0));
  const top = Math.max(1, ...g.edges.map((e: any) => e.count || 0));
  return (
    <>
      <g className="pm-frames">
        {lay.hulls.map((f) => {
          const k = (g.kinds || []).find((x: any) => x.name === f.name) || {};
          return (
            <g key={f.name} className="pm-frame hull" data-kind={f.name}>
              <rect x={f.x} y={f.y} width={f.width} height={f.height} rx={6} fill="none" stroke="var(--frame, #bbb)" />
              <text x={f.x + 14} y={f.y + 18} className="pm-title">
                {f.name}<tspan className="t-sub" dx={8}>{`${k.items ?? ""} item${k.items === 1 ? "" : "s"}${k.by ? ` · ${k.by}` : ""}`}</tspan>
              </text>
            </g>
          );
        })}
      </g>
      <g>
        {lay.edges.map((le) => {
          const e = edgeById[le.id], pts = edgePoints(le);
          if (!e || pts.length < 2) return null;
          const w = 1.2 + 4.8 * Math.sqrt((e.count || 0) / top);
          const t = pmLabel(e, show), lb = le.labels?.[0], m = midOf(pts);
          return (
            <g key={le.id} className={["edge", "pm-" + e.kind, e.rework ? "rework" : ""].join(" ")} data-id={e.id}>
              <path d={roundedPath(pts, 6)} fill="none" stroke="var(--ink)" strokeOpacity={0.55} strokeWidth={w} />
              <path d={arrowHead(pts, 8 + w)} fill="var(--ink)" fillOpacity={0.7} />
              {t && <text x={lb ? lb.x + lb.width / 2 : m.x} y={lb ? lb.y + 11 : m.y - 5} textAnchor="middle" className="t-sub elabel"
                paintOrder="stroke" stroke="var(--bg)" strokeWidth={4}>{t}</text>}
              <path d={roundedPath(pts, 6)} className="edge-hit" />
            </g>
          );
        })}
      </g>
      <g>
        {lay.children.map((c) => {
          const n = byId[c.id];
          if (!n) return null;
          return (
            <g key={n.id} className={`node k-${n.kind} pm-node${acts.sel === n.id ? " sel" : ""}`} transform={`translate(${c.x},${c.y})`} data-id={n.id}
              onClick={() => acts.pick(n)}>
              <PmNode n={n} w={c.width} h={c.height} most={most} />
            </g>
          );
        })}
      </g>
    </>
  );
}
export { PM };
