import { projectionHref } from "../lib/hrefs";

/* A projection's graph of states (SPEC §5a, *The projection's page*): its states as chips with how many items are in
   each now, and an arrow only for a move its items have made (from the listing's `moves`, which the item index counts
   as it folds them), with how many times; never the declared list with an arrow between neighbours. Laid out left to
   right in the order items pass through (each state after the states that lead into it, a side exit branching off
   where it leaves), a move back to an earlier state drawn under the chips as a back edge; the moves into a state from
   nowhere (its arrivals) as an entry from the left; a finishing state boxed double. The states no item has reached
   follow in one muted line. Small and plain: chips are HTML (each filters the list, as before), the lines an SVG under
   them. */

export type Move = { from: string | null; to: string; n: number };

const COL_GAP = 56, ROW_H = 24, ROW_GAP = 8, ENTRY = 30, CH = 7.2, PAD = 22, BACK = 16;

export type Layout = {
  nodes: { st: string; x: number; y: number; w: number; rank: number }[];
  edges: { from: string; to: string; n: number; back: boolean }[];
  entries: { to: string; n: number }[];
  unreached: string[];
  width: number; height: number;
};

/** Where each state goes: its rank (the longest way into it, back edges left out) and its row in that rank. */
export function layoutStates(states: string[], counts: Record<string, number>, moves: Move[]): Layout {
  const order = [...states];
  for (const m of moves) for (const s of [m.from, m.to]) if (s && !order.includes(s)) order.push(s);
  for (const s of Object.keys(counts)) if (s && counts[s] && !order.includes(s)) order.push(s);
  const idx = (s: string) => order.indexOf(s);
  const moved = moves.filter((m) => m.from && m.from !== m.to) as { from: string; to: string; n: number }[];
  const entries = moves.filter((m) => !m.from).map((m) => ({ to: m.to, n: m.n }));
  const active = new Set<string>([...moved.flatMap((m) => [m.from, m.to]), ...entries.map((e) => e.to),
    ...order.filter((s) => counts[s])]);
  const nodes = order.filter((s) => active.has(s));
  const out = new Map<string, string[]>(nodes.map((s) => [s, []]));
  for (const m of moved) out.get(m.from)!.push(m.to);
  for (const v of out.values()) v.sort((a, b) => idx(a) - idx(b));
  // back edges: a move to a state still on the way (a depth-first walk from the entries, then the rest, in order)
  const back = new Set<string>(), seen = new Set<string>(), on = new Set<string>();
  const walk = (s: string) => {
    seen.add(s); on.add(s);
    for (const t of out.get(s)!) {
      if (on.has(t)) back.add(`${s}\u0000${t}`);
      else if (!seen.has(t)) walk(t);
    }
    on.delete(s);
  };
  for (const s of [...entries.map((e) => e.to).sort((a, b) => idx(a) - idx(b)), ...nodes]) if (!seen.has(s)) walk(s);
  const fwd = moved.filter((m) => !back.has(`${m.from}\u0000${m.to}`));
  const rank = new Map<string, number>(nodes.map((s) => [s, 0]));
  for (let i = 0; i < nodes.length; i++) {             // longest path, relaxed (a DAG once back edges are out)
    let changed = false;
    for (const m of fwd) {
      const r = rank.get(m.from)! + 1;
      if (r > rank.get(m.to)!) { rank.set(m.to, r); changed = true; }
    }
    if (!changed) break;
  }
  const ranks: string[][] = [];
  for (const s of nodes) (ranks[rank.get(s)!] ||= []).push(s);
  const row = new Map<string, number>();
  ranks.forEach((col, r) => {                          // each column ordered by where its sources sit, then in order
    const bary = (s: string) => {
      const ins = fwd.filter((m) => m.to === s && row.has(m.from)).map((m) => row.get(m.from)!);
      return ins.length ? ins.reduce((a, b) => a + b, 0) / ins.length : Infinity;
    };
    if (r > 0) col.sort((a, b) => bary(a) - bary(b) || idx(a) - idx(b));
    col.forEach((s, i) => row.set(s, i));
  });
  const wOf = (s: string) => Math.round((s.length + String(counts[s] || 0).length) * CH + PAD);
  const colW = ranks.map((col) => Math.max(...(col || []).map(wOf), 0));
  const x0 = entries.length ? ENTRY : 0;
  const colX: number[] = [];
  colW.reduce((x, w, i) => { colX[i] = x; return x + w + COL_GAP; }, x0);
  const tall = Math.max(1, ...ranks.map((c) => (c || []).length));
  const placed = nodes.map((s) => ({ st: s, rank: rank.get(s)!, x: colX[rank.get(s)!], y: row.get(s)! * (ROW_H + ROW_GAP), w: colW[rank.get(s)!] }));
  const hasBack = moved.some((m) => back.has(`${m.from}\u0000${m.to}`));
  return {
    nodes: placed,
    edges: moved.map((m) => ({ ...m, back: back.has(`${m.from}\u0000${m.to}`) })),
    entries,
    unreached: order.filter((s) => !active.has(s)),
    width: nodes.length ? colX[colX.length - 1] + colW[colW.length - 1] : 0,
    height: nodes.length ? tall * (ROW_H + ROW_GAP) - ROW_GAP + (hasBack ? BACK + 12 : 0) : 0,
  };
}

export function StateGraph({ k, state, onState }: {
  k: any; state?: string | null; onState?: (st: string | null) => void;
}) {
  const counts: Record<string, number> = k.counts || {};
  const moves: Move[] = k.moves || [];
  const ends = new Set<string>(k.lives_on ? [] : [...(k.finished || []), ...(k.final || [])]);
  const L = layoutStates(k.states || [], counts, moves);
  const at = new Map(L.nodes.map((n) => [n.st, n]));
  const chip = (st: string, style?: React.CSSProperties) => (
    <a key={st} href={projectionHref(k.name, `state=${encodeURIComponent(st)}`)} style={style} data-state={st}
      className={`stbox${counts[st] ? " some" : ""}${state === st ? " on" : ""}${ends.has(st) ? " final" : ""}`}
      aria-pressed={state === st} title={ends.has(st) ? `${st}: finishes` : st}
      onClick={(ev) => { ev.preventDefault(); onState?.(state === st ? null : st); }}>
      <span className="n">{String(counts[st] || 0)}</span>{st}
    </a>
  );
  if (!moves.length) {                                // no move known (a draft, a record kept nowhere): the chips alone
    return <div className="state-graph states" data-moves={0}>{[...(k.states || []), ...L.unreached.filter((s) => !(k.states || []).includes(s))]
      .filter((s, i, a) => a.indexOf(s) === i).map((st: string) => chip(st))}</div>;
  }
  const mid = (n: { y: number }) => n.y + ROW_H / 2;
  const bottom = L.height - (L.edges.some((e) => e.back) ? 4 : 0);
  return (
    <div className="state-graph" data-moves={moves.length}>
      {L.nodes.length > 0 && (
        <div className="sg-canvas" style={{ width: L.width, height: L.height }}>
          <svg width={L.width} height={L.height} aria-hidden="true">
            <defs>
              <marker id="sg-head" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L8,4 L0,8 z" className="sg-head" />
              </marker>
            </defs>
            {L.entries.map((e) => {
              const n = at.get(e.to)!;
              return (
                <g key={`in-${e.to}`} className="sg-entry" data-to={e.to}>
                  <path d={`M${n.x - ENTRY + 2},${mid(n)} L${n.x - 1},${mid(n)}`} markerEnd="url(#sg-head)" />
                  <text x={n.x - ENTRY / 2} y={mid(n) - 4} textAnchor="middle">{e.n}</text>
                </g>
              );
            })}
            {L.edges.map((e) => {
              const a = at.get(e.from)!, b = at.get(e.to)!;
              let d: string, lx: number, ly: number;
              if (e.back) {                               // under the chips, right to left
                const x1 = a.x + a.w / 2, x2 = b.x + b.w / 2, y1 = a.y + ROW_H, y2 = b.y + ROW_H;
                d = `M${x1},${y1} C${x1},${bottom} ${x2},${bottom} ${x2},${y2 + 1}`;
                lx = (x1 + x2) / 2; ly = bottom - 2;
              } else {
                const x1 = a.x + a.w, x2 = b.x - 1, y1 = mid(a), y2 = mid(b), c = (x2 - x1) / 2;
                d = `M${x1},${y1} C${x1 + c},${y1} ${x2 - c},${y2} ${x2},${y2}`;
                lx = (x1 + x2) / 2; ly = (y1 + y2) / 2 - 4;
              }
              return (
                <g key={`${e.from}>${e.to}`} className={`sg-edge${e.back ? " back" : ""}`} data-from={e.from} data-to={e.to} data-n={e.n}>
                  <title>{`${e.from} → ${e.to}: ${e.n} time${e.n === 1 ? "" : "s"}`}</title>
                  <path d={d} markerEnd="url(#sg-head)" />
                  <text x={lx} y={ly} textAnchor="middle">{e.n}</text>
                </g>
              );
            })}
          </svg>
          {L.nodes.map((n) => chip(n.st, { left: n.x, top: n.y, width: n.w, height: ROW_H }))}
        </div>
      )}
      {L.unreached.length > 0 && (
        <p className="sg-unreached muted small">
          {L.nodes.length ? "not reached yet: " : ""}
          {L.unreached.map((st) => chip(st))}
        </p>
      )}
    </div>
  );
}
