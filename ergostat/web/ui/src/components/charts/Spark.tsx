import { fmt } from "../../lib/format";

/** A small line of a series against its setpoint (details.js sparkSvg). */
export function Spark({ points, w, h: hgt, setpoint = null }: { points: [number, number][]; w: number; h: number; setpoint?: number | null }) {
  const vs = points.map((p) => p[1]);
  let lo = Math.min(...vs), hi = Math.max(...vs);
  if (setpoint != null) { lo = Math.min(lo, setpoint); hi = Math.max(hi, setpoint); }
  const small = hgt < 50, pad = small ? 3 : 6, left = small ? 2 : 34;
  const y = (v: number) => hgt - pad - ((v - lo) / ((hi - lo) || 1)) * (hgt - 2 * pad);
  const d = vs.map((v, i) => `${i ? "L" : "M"}${left + (i / (vs.length - 1)) * (w - left - 4)},${y(v)}`).join("");
  return (
    <svg width={w} height={hgt} className="spark">
      {setpoint != null && <line x1={left} x2={w - 2} y1={y(setpoint)} y2={y(setpoint)} className="chart-set" />}
      <path d={d} className="chart-line" />
      {!small && <><text x={0} y={12} className="chart-tick">{fmt(hi)}</text><text x={0} y={hgt - 2} className="chart-tick">{fmt(lo)}</text></>}
    </svg>
  );
}
