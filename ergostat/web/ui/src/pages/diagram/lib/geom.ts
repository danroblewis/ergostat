/* Plain geometry for the diagram: no DOM, no React (ported from diagram.js, dynamics.js). */
export interface Pt { x: number; y: number }

export const CH = 6.7; // px per character, for label sizes
export const textWidth = (t: string | null | undefined): number => String(t ?? "").length * CH;

/** A polyline with its corners rounded by ``r``. */
export function roundedPath(pts: Pt[], r = 7): string {
  if (pts.length < 2) return "";
  let d = `M${pts[0].x},${pts[0].y}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const a = pts[i - 1], b = pts[i], c = pts[i + 1];
    const l1 = Math.hypot(b.x - a.x, b.y - a.y), l2 = Math.hypot(c.x - b.x, c.y - b.y);
    const k = Math.min(r, l1 / 2, l2 / 2);
    if (!k) { d += ` L${b.x},${b.y}`; continue; }
    const p1 = { x: b.x - ((b.x - a.x) / l1) * k, y: b.y - ((b.y - a.y) / l1) * k };
    const p2 = { x: b.x + ((c.x - b.x) / l2) * k, y: b.y + ((c.y - b.y) / l2) * k };
    d += ` L${p1.x},${p1.y} Q${b.x},${b.y} ${p2.x},${p2.y}`;
  }
  const z = pts[pts.length - 1];
  return d + ` L${z.x},${z.y}`;
}

/** The line, its last ``by`` px cut off (where a head goes). */
export function shortened(pts: Pt[], by: number): Pt[] {
  const out = pts.slice();
  const b = out[out.length - 1], a = out[out.length - 2];
  const L = Math.hypot(b.x - a.x, b.y - a.y);
  if (L <= by) return out;
  out[out.length - 1] = { x: b.x - ((b.x - a.x) / L) * by, y: b.y - ((b.y - a.y) / L) * by };
  return out;
}

/** An arrowhead's path at the end of ``pts``. */
export function arrowHead(pts: Pt[], size = 7): string {
  const a = pts[pts.length - 2], b = pts[pts.length - 1];
  const ang = Math.atan2(b.y - a.y, b.x - a.x), w = size * 0.55;
  const bx = b.x - size * Math.cos(ang), by = b.y - size * Math.sin(ang);
  const px = -Math.sin(ang) * w, py = Math.cos(ang) * w;
  return `M${bx + px},${by + py} L${b.x},${b.y} L${bx - px},${by - py} Z`;
}

/** A flow's hollow head, wider than its pipe. */
export function pipeHead(pts: Pt[]): string {
  const a = pts[pts.length - 2], b = pts[pts.length - 1];
  const ang = Math.atan2(b.y - a.y, b.x - a.x), L = 15, Wd = 9;
  const bx = b.x - L * Math.cos(ang), by = b.y - L * Math.sin(ang);
  const px = -Math.sin(ang) * Wd, py = Math.cos(ang) * Wd;
  return `M${bx + px},${by + py} L${b.x},${b.y} L${bx - px},${by - py} Z`;
}

/** A connector's curve: a gentle bow for two points, quadratic through the middle of the rest. */
export function curve(pts: Pt[]): { d: string; tail: Pt; tip: Pt } {
  const n = pts.length;
  if (n === 2) {
    const [a, b] = pts, L = Math.hypot(b.x - a.x, b.y - a.y);
    const bow = L > 60 ? Math.min(0.1 * L, 18) : 0;
    if (!bow) return { d: `M${a.x},${a.y} L${b.x},${b.y}`, tail: a, tip: b };
    const c = { x: (a.x + b.x) / 2 - ((b.y - a.y) / L) * bow, y: (a.y + b.y) / 2 + ((b.x - a.x) / L) * bow };
    return { d: `M${a.x},${a.y} Q${c.x},${c.y} ${b.x},${b.y}`, tail: c, tip: b };
  }
  const m = (a: Pt, b: Pt) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
  let d = `M${pts[0].x},${pts[0].y}`;
  for (let i = 1; i < n - 1; i++) {
    const to = i === n - 2 ? pts[n - 1] : m(pts[i], pts[i + 1]);
    d += ` Q${pts[i].x},${pts[i].y} ${to.x},${to.y}`;
  }
  return { d, tail: pts[n - 2], tip: pts[n - 1] };
}

/** Words in lines of ``room`` characters, ``max`` lines at most (the last cut with …). */
export function wrapWords(text: string, room: number, max: number): string[] {
  const lines = [""];
  for (const wd of text.split(/\s+/)) {
    const cur = lines[lines.length - 1];
    if (cur && (cur + " " + wd).length > room) lines.push(wd);
    else lines[lines.length - 1] = cur ? cur + " " + wd : wd;
  }
  if (lines.length > max) lines.splice(max - 1, lines.length, lines.slice(max - 1).join(" ").slice(0, room - 1) + "…");
  return lines;
}

/** An ELK edge's points, start, bends and end, in one list. */
export function edgePoints(le: any): Pt[] {
  const s = le.sections?.[0];
  if (!s) return [];
  return [s.startPoint, ...(s.bendPoints || []), s.endPoint].map((p: Pt) => ({ x: p.x, y: p.y }));
}

/** The middle of a line's longest segment. */
export function midOf(pts: Pt[]): Pt & { vertical: boolean } {
  let best = [pts[0], pts[1]], len = -1;
  for (let i = 1; i < pts.length; i++) {
    const d = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
    if (d > len) { len = d; best = [pts[i - 1], pts[i]]; }
  }
  return { x: (best[0].x + best[1].x) / 2, y: (best[0].y + best[1].y) / 2, vertical: Math.abs(best[0].x - best[1].x) < 1 };
}
