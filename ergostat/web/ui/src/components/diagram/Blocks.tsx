import { arrowHead, edgePoints, midOf, roundedPath } from "./geom";
import { bdCaption, UPKEEP, type Layout } from "./layout";
import type { Acts } from "./Dynamics";

/* The Blocks view: the control system as a block diagram (blocks.js's bdNode, simplified: no fractions, sketches,
   mux bars' counts or frames around each system). */

function Sym({ fn, x, y, anchor = "middle", size = 13 }: { fn: any; x: number; y: number; anchor?: "start" | "middle" | "end"; size?: number }) {
  return (
    <text x={x} y={y} className="bd-sym" textAnchor={anchor} fontSize={size}>
      {fn?.sym && <tspan className={(fn.named ? "bd-sysname" : "bd-mi") + (fn.bold ? " bd-bold" : "")}>{fn.sym}</tspan>}
      {fn?.sub && <tspan className="bd-subs" baselineShift="sub" fontSize={size * 0.74}>{fn.sub}</tspan>}
      {fn?.arg && <>(<tspan className="bd-mi">{fn.arg}</tspan>)</>}
    </text>
  );
}

function BlockBody({ n, w, h }: { n: any; w: number; h: number }) {
  const fn = n.fn || {};
  if (n.role === "sensor" || n.role === "collector") {
    const reads: string[] = [].concat(fn.reads || []).map(String);
    return (
      <g>
        <rect className="hit bd-line bd-fill" width={w} height={h} />
        <text x={w / 2} y={20} className={n.role === "collector" ? "bd-name" : "bd-expr"} textAnchor="middle">{fn.head || fn.sym || n.label}</text>
        {reads.map((l, i) => <text key={i} x={w / 2} y={36 + i * 13} className="bd-note" textAnchor="middle">{l}</text>)}
      </g>
    );
  }
  if (n.kind === "sum") return <circle className="hit bd-line bd-fill" cx={w / 2} cy={h / 2} r={w / 2} />;
  if (n.kind === "mux" || n.kind === "demux") return <rect className="hit bd-bar" width={w} height={h} />;
  if (n.kind === "input" || n.kind === "output") {
    const inp = n.kind === "input";
    return (
      <g>
        <rect className="hit bd-ghost" width={w} height={h} />
        <Sym fn={fn} x={inp ? w - 4 : 4} y={h / 2 + 4} anchor={inp ? "end" : "start"} />
        {fn.value && <text x={inp ? w - 4 : 4} y={h + 10} className="bd-note" textAnchor={inp ? "end" : "start"}>{fn.value}</text>}
      </g>
    );
  }
  if (n.kind === "port") {
    return <g><rect className="hit bd-line bd-fill" width={w} height={h} rx={h / 2} /><Sym fn={fn} x={w / 2} y={h / 2 + 4} size={12} /></g>;
  }
  const cap = bdCaption(n), band = cap ? 12 : 0, bh = h - band - (n.upkeep ? 16 : 0);
  return (
    <g>
      <rect className="hit bd-line bd-fill" width={w} height={h} strokeDasharray={n.upkeep ? "6 4" : undefined} />
      {cap && <text x={5} y={13} className="bd-note bd-tier" data-tier={n.tier || ""}>{cap}</text>}
      <g transform={band ? `translate(0,${band})` : undefined}>
        {fn.name
          ? <text x={w / 2} y={bh / 2 + 4} className="bd-name bd-main" textAnchor="middle">{fn.name}</text>
          : <>
              <Sym fn={fn} x={w / 2} y={fn.expr ? bh / 2 - 2 : bh / 2 + 5} />
              {fn.expr && <text x={w / 2} y={bh / 2 + 14} className="bd-note" textAnchor="middle">{fn.expr}</text>}
              {n.role === "subsystem" && n.size && <text x={w / 2} y={bh / 2 + 18} className="bd-note" textAnchor="middle">{n.size}</text>}
            </>}
      </g>
      {n.upkeep && <text x={w / 2} y={h - 8} className="bd-note sys-upkeep" textAnchor="middle">{UPKEEP}</text>}
      {(n.identified || n.declared) && <text x={w} y={-5} className="bd-note bd-ident" textAnchor="end">{n.identified ? "identified" : n.declared}</text>}
      {n.alarm && <text x={0} y={-5} className="bd-note bd-alarm s-off">alarm {n.alarm}</text>}
    </g>
  );
}

export function BlocksDrawing({ g, lay, acts }: { g: any; lay: Layout; acts: Acts }) {
  const byId: Record<string, any> = Object.fromEntries(g.nodes.map((n: any) => [n.id, n]));
  const edgeById: Record<string, any> = Object.fromEntries(g.edges.map((e: any) => [e.id, e]));
  return (
    <>
      <g>
        {lay.edges.map((le) => {
          const e = edgeById[le.id], pts = edgePoints(le);
          if (!e || pts.length < 2) return null;
          const m = midOf(pts), sig = e.signal || {};
          return (
            <g key={le.id} className="edge bd-edge" data-id={e.id} data-nodes={`${e.source} ${e.target}`}>
              <path d={roundedPath(pts, 4)} className="bd-wire" />
              <path d={arrowHead(pts, 8)} className="bd-head" />
              {(sig.sym || sig.sub) && (
                <text x={m.vertical ? m.x + 6 : m.x} y={m.vertical ? m.y + 4 : m.y - 6} textAnchor={m.vertical ? "start" : "middle"} className="bd-sym bd-signal" fontSize={12}>
                  <tspan className="bd-mi">{sig.sym}</tspan>
                  {sig.sub && <tspan className="bd-subs" baselineShift="sub" fontSize={9}>{sig.sub}</tspan>}
                </text>
              )}
              <path d={roundedPath(pts, 4)} className="edge-hit" />
            </g>
          );
        })}
      </g>
      <g>
        {lay.children.map((c) => {
          const n = byId[c.id];
          if (!n) return null;
          return (
            <g key={n.id} className={`node bd-node bd-${n.kind} bd-${n.role || n.kind}${acts.sel === n.id ? " sel" : ""}`}
              transform={`translate(${c.x},${c.y})`} data-id={n.id} onClick={() => acts.pick(n)}
              onDoubleClick={() => { if (n.role === "subsystem") acts.toggleSystem(n.system || n.label); }}>
              <title>{n.says || n.label}</title>
              <BlockBody n={n} w={c.width} h={c.height} />
            </g>
          );
        })}
      </g>
    </>
  );
}
