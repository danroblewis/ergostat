import { arrowHead, curve, edgePoints, pipeHead, roundedPath, shortened, textWidth } from "./lib/geom";
import { nameOf, portSide, sdAuxLines, sdLabelLines, sdNoUnit, sdValue, SYS_ROW, SYS_TOP, systemDescLines, UPKEEP, type Layout } from "./lib/layout";

/* The Dynamics view: stocks, flows (pipes with their valves), clouds, auxiliaries, connectors, and closed systems as
   modules with their connection points (dynamics.js's SD_DRAW and sdEdgeContent). Class names are the old page's. */

const MINUS = "−";
const sign = (p: string | null) => (p === "+" ? "+" : p === "-" ? MINUS : null);
const goalsOff = (n: any) => n.status === "off" || (n.loops?.off ?? 0) > 0;

export interface Acts {
  pick: (n: any) => void;
  pickEdge?: (e: any) => void;
  toggleSystem: (name: string) => void;
  drill: (name: string) => void;
  sel: string | null;
}

function Stock({ n, w, h }: { n: any; w: number; h: number }) {
  const v = sdValue(n);
  return (
    <g>
      <rect className="hit sd-stock" width={w} height={h} strokeDasharray={n.outside ? "5 4" : undefined} />
      <text x={w / 2} y={v ? 19 : h / 2 + 4} textAnchor="middle" className="t-label sd-name">{nameOf(n)}</text>
      {v && (
        <text x={w / 2} y={34} textAnchor="middle" className="t-sub sd-value live">
          {v}{sdNoUnit(n) && <tspan className="sd-nounit"> unit ?</tspan>}
        </text>
      )}
    </g>
  );
}

function Aux({ n, w, h }: { n: any; w: number; h: number }) {
  return (
    <g>
      <rect className="hit sd-aux" width={w} height={h} rx={3} />
      {sdAuxLines(n).map((t, i) => (
        <text key={i} x={w / 2} y={14 + i * 14} textAnchor="middle"
          className={i === 0 ? "t-label sd-name" : t === "(exogenous)" ? "t-sub sd-exo" : t.startsWith("→") ? "t-sub sd-exo sd-nofeedback" : "t-sub sd-value" + (n.role === "desired" ? "" : " live")}>
          {t}
        </text>
      ))}
    </g>
  );
}

function Valve({ w, h }: { w: number; h: number }) {
  const pipe = `M0,${h / 2} H${w}`;
  return (
    <g>
      <rect className="hit" x={-2} y={-2} width={w + 4} height={h + 4} rx={6} fill="transparent" stroke="transparent" />
      <path d={pipe} className="sd-pipe-out" />
      <path d={pipe} className="sd-pipe-in" />
      <path className="sd-valve" d={`M6,9 L${w / 2},${h / 2} L6,${h - 9} Z M${w - 6},9 L${w / 2},${h / 2} L${w - 6},${h - 9} Z`} />
    </g>
  );
}

function Cloud({ w, h }: { w: number; h: number }) {
  const d = `M${w * 0.22},${h * 0.82} C${w * 0.02},${h * 0.82} ${w * 0.02},${h * 0.42} ${w * 0.22},${h * 0.45}
             C${w * 0.22},${h * 0.12} ${w * 0.55},${h * 0.08} ${w * 0.6},${h * 0.32}
             C${w * 0.7},${h * 0.12} ${w * 0.95},${h * 0.22} ${w * 0.86},${h * 0.5}
             C${w * 1.02},${h * 0.56} ${w * 0.98},${h * 0.84} ${w * 0.8},${h * 0.82} Z`;
  return <g><path className="hit sd-cloud" d={d} /></g>;
}

function Terminal({ n, w, h }: { n: any; w: number; h: number }) {
  const stub = n.role === "stub";
  return (
    <g>
      <rect className="hit" width={w} height={h} rx={4} fill="transparent" stroke="transparent" />
      <text x={stub ? 2 : w / 2} y={h / 2 + 4} textAnchor={stub ? "start" : "middle"} className="t-sub sd-shadow">{stub ? n.label : `<${n.label}>`}</text>
    </g>
  );
}

function SysBtn({ x, label, title, onClick }: { x: number; label: string; title: string; onClick: () => void }) {
  return (
    <g className="sys-btn" transform={`translate(${x},10)`} onClick={(ev) => { ev.stopPropagation(); onClick(); }}>
      <title>{title}</title>
      <rect width={textWidth(label) + 14} height={20} rx={4} />
      <text x={7} y={14}>{label}</text>
    </g>
  );
}

function System({ n, w, h, acts }: { n: any; w: number; h: number; acts: Acts }) {
  const said = systemDescLines(n, w);
  const at = { west: 0, east: 0 };
  const into = "Into", open = "Open";
  return (
    <g className={n.remote ? `sys-remote remote-${n.remote.state}` : undefined}>
      <rect className={"hit sd-module" + (goalsOff(n) ? " sys-off" : "")} width={w} height={h} rx={8}
        strokeDasharray={n.upkeep ? "6 4" : n.remote ? "9 5" : undefined} />
      <text x={16} y={24} className="t-label sys-title">{nameOf(n)}</text>
      {said.map((t, i) => <text key={i} x={16} y={42 + i * 14} className={"t-sub sys-desc" + (n.remote ? " live" : "")}>{t}</text>)}
      {n.upkeep && <text x={16} y={44 + said.length * 14} className="t-sub sys-upkeep">{UPKEEP}</text>}
      <SysBtn x={w - textWidth(into) - 24} label={into} title="Draw this system alone, with what it reaches outside at its edge" onClick={() => acts.drill(n.label)} />
      <SysBtn x={w - textWidth(into) - textWidth(open) - 46} label={open} title="Open it here: its parts in place of the box" onClick={() => acts.toggleSystem(n.label)} />
      {(n.ports || []).map((p: any) => {
        const side = portSide(p), left = side === "west";
        const y = SYS_TOP + at[side]++ * SYS_ROW;
        return (
          <text key={p.id} x={left ? 8 : w - 8} y={y + 4} className="t-sub sd-port-name" textAnchor={left ? "start" : "end"} data-part={p.part} data-side={side}>
            <title>{p.label}</title>
            {nameOf(p)}
            {p.value && <tspan className="live" dx={6} opacity={0.75}>{p.value}</tspan>}
          </text>
        );
      })}
    </g>
  );
}

function Part({ n, w, h, acts }: { n: any; w: number; h: number; acts: Acts }) {
  switch (n.kind) {
    case "stock": return <Stock n={n} w={w} h={h} />;
    case "auxiliary": return <Aux n={n} w={w} h={h} />;
    case "valve": case "disturbance": return <Valve w={w} h={h} />;
    case "cloud": return <Cloud w={w} h={h} />;
    case "system": return <System n={n} w={w} h={h} acts={acts} />;
    case "terminal": return <Terminal n={n} w={w} h={h} />;
    default: return <rect className="hit" width={w} height={h} rx={4} />;
  }
}

function Edge({ e, le, g }: { e: any; le: any; g: any }) {
  const pts = edgePoints(le);
  if (pts.length < 2) return null;
  const loopSt = (e.loops || []).map((k: string) => g.loops?.[k]?.status).find(Boolean);
  const cls = ["edge", e.kind, loopSt ? "loop-" + loopSt : ""].filter(Boolean).join(" ");
  if (e.kind === "pipe") {
    const two = e.twoWay && !e.arrow;
    let body = e.arrow ? shortened(pts, 14) : pts;
    if (two) body = shortened(body.slice().reverse(), 14).reverse();
    const bd = roundedPath(body, 10);
    const head = { fill: "var(--sd-paper)", stroke: "var(--sd-ink)", strokeWidth: 1.6, strokeLinejoin: "round" as const };
    return (
      <g className={cls} data-id={e.id} data-nodes={`${e.source} ${e.target}`}>
        <path d={bd} className="pipe-out" />
        <path d={bd} className="pipe-in" />
        {e.arrow && <path className="pipe-head" d={pipeHead(pts)} style={head} />}
        {two && <path className="pipe-tail" d={pipeHead(pts.slice().reverse())} style={head} />}
        <path d={roundedPath(pts, 10)} className="edge-hit" />
      </g>
    );
  }
  const c = curve(pts);
  const s = sign(e.polarity);
  const ang = Math.atan2(c.tip.y - c.tail.y, c.tip.x - c.tail.x);
  // its sign beside its head: back along the line and to its left (sdPlaceSigns searches; this only steps aside)
  const sx = c.tip.x - 14 * Math.cos(ang) + 9 * Math.sin(ang), sy = c.tip.y - 14 * Math.sin(ang) - 9 * Math.cos(ang) + 4;
  return (
    <g className={cls} data-id={e.id} data-nodes={`${e.source} ${e.target}`}>
      <path d={c.d} className={"info sd-connector" + (e.drivenBy ? " driven-by" : "")} />
      <path d={arrowHead([c.tail, c.tip], 7)} className="head sd-head" />
      <text x={sx} y={sy} textAnchor="middle" className={"polarity" + (s ? "" : " unknown")} paintOrder="stroke" data-edge={e.id}>{s || "?"}</text>
      <path d={roundedPath(pts, 7)} className="edge-hit" />
    </g>
  );
}

export function DynamicsDrawing({ g, lay, acts }: { g: any; lay: Layout; acts: Acts }) {
  const byId: Record<string, any> = Object.fromEntries(g.nodes.map((n: any) => [n.id, n]));
  const edgeById: Record<string, any> = Object.fromEntries(g.edges.map((e: any) => [e.id, e]));
  return (
    <>
      <g className="hulls">
        {lay.hulls.map((h) => (
          <g key={h.name} className="hull">
            <rect x={h.x} y={h.y} width={h.width} height={h.height} rx={6} fill="none" stroke="var(--frame, #bbb)" strokeDasharray="4 3" />
            <text x={h.x + 12} y={h.y + 4} className="sys-hull-label" onClick={(ev) => { ev.stopPropagation(); acts.toggleSystem(h.name); }}>{h.name} ▾</text>
          </g>
        ))}
      </g>
      <g>{lay.edges.map((le) => edgeById[le.id] && <Edge key={le.id} e={edgeById[le.id]} le={le} g={g} />)}</g>
      <g>
        {lay.children.map((ln) => {
          const n = byId[ln.id];
          if (!n) return null;
          const lb = ln.labels?.[0];
          const lines = lb ? sdLabelLines(n) : [];
          return (
            <g key={n.id} className={`node k-${n.kind}${acts.sel === n.id ? " sel" : ""}`} transform={`translate(${ln.x},${ln.y})`} data-id={n.id}
              onClick={() => acts.pick(n)} onDoubleClick={(ev) => { if (n.kind === "system") { ev.stopPropagation(); acts.toggleSystem(n.label); } }}>
              <title>{n.label}</title>
              <Part n={n} w={ln.width} h={ln.height} acts={acts} />
              {lb && lines.map((t: string, i: number) => (
                <text key={i} x={lb.x + lb.width / 2} y={lb.y + 13 + i * 16} textAnchor="middle"
                  className={n.kind === "cloud" ? "t-sub sd-shadow" : i === 0 ? "t-label sd-name" : "t-sub sd-value live"}>{t}</text>
              ))}
            </g>
          );
        })}
      </g>
    </>
  );
}
