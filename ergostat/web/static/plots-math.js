/* the arithmetic of the chart forms, kept free of the page so each result can be checked against a known answer:
   quartiles, whiskers, bins, a least-squares line, a density estimate, phase unwrapping and axis ticks */
"use strict";

const plotMath = (() => {
  const finite = (xs) => xs.filter((v) => v != null && Number.isFinite(v));
  const ascending = (xs) => finite(xs).sort((a, b) => a - b);

  /* linear interpolation between order statistics (Hyndman and Fan's type 7, numpy's default) */
  function quantile(sorted, p) {
    if (!sorted.length) return null;
    const at = (sorted.length - 1) * p, lo = Math.floor(at), hi = Math.ceil(at);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (at - lo);
  }

  /* whiskers: tukey reaches the furthest datum within 1.5 IQR of the box; p5-p95 are those percentiles; min-max
     the extremes, so it has no outliers */
  function boxStats(values, whiskers = "tukey") {
    const xs = ascending(values);
    if (!xs.length) return null;
    const q1 = quantile(xs, 0.25), median = quantile(xs, 0.5), q3 = quantile(xs, 0.75), iqr = q3 - q1;
    let lo, hi;
    if (whiskers === "min-max") { lo = xs[0]; hi = xs[xs.length - 1]; }
    else if (whiskers === "p5-p95") { lo = quantile(xs, 0.05); hi = quantile(xs, 0.95); }
    else {
      const low = q1 - 1.5 * iqr, high = q3 + 1.5 * iqr;
      lo = xs.find((v) => v >= low);
      hi = [...xs].reverse().find((v) => v <= high);
    }
    return { n: xs.length, q1, median, q3, lo, hi, outliers: xs.filter((v) => v < lo || v > hi),
             mean: xs.reduce((a, b) => a + b, 0) / xs.length, min: xs[0], max: xs[xs.length - 1] };
  }

  /* statistics the answer worked out over every value: a whisker rule picks from them. Statistics with no percentiles
     are drawn exactly as given */
  function boxFrom(given, whiskers = "tukey", sample = []) {
    const out = { outliers: [], ...given };
    if (given.p5 == null) return out;
    if (whiskers === "min-max") return { ...out, lo: given.min, hi: given.max, outliers: [], outliers_more: 0 };
    if (whiskers === "p5-p95") {
      const beyond = finite(sample).filter((v) => v < given.p5 || v > given.p95);
      return { ...out, lo: given.p5, hi: given.p95, outliers: beyond, outliers_more: 0, sampled: given.n > sample.length };
    }
    return out;
  }

  /* the Freedman-Diaconis width, falling back on Sturges when the middle half of the data has no spread */
  function autoBins(values) {
    const xs = ascending(values);
    if (xs.length < 2 || xs[0] === xs[xs.length - 1]) return 1;
    const iqr = quantile(xs, 0.75) - quantile(xs, 0.25);
    const sturges = Math.ceil(Math.log2(xs.length)) + 1;
    if (iqr <= 0) return Math.min(60, sturges);
    const width = 2 * iqr / Math.cbrt(xs.length);
    return Math.max(1, Math.min(60, Math.ceil((xs[xs.length - 1] - xs[0]) / width)));
  }
  function edgesOver(lo, hi, bins) {
    if (lo === hi) { lo -= 0.5; hi += 0.5; }
    return Array.from({ length: bins + 1 }, (_, i) => lo + (hi - lo) * i / bins);
  }
  /* bins are closed on the left, and the last on both sides, so every value is counted once */
  function countInto(values, edges) {
    const counts = new Array(edges.length - 1).fill(0), last = counts.length - 1;
    for (const v of finite(values)) {
      if (v < edges[0] || v > edges[last + 1]) continue;
      let lo = 0, hi = last;
      while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (edges[mid] <= v) lo = mid; else hi = mid - 1; }
      counts[lo]++;
    }
    return counts;
  }
  /* an answer's X for bins: its edges (one more than the counts), or its centres, from which the edges are found */
  function edgesFromX(xs, n) {
    if (xs.length === n + 1) return xs.slice();
    if (xs.length !== n || !n) return null;
    if (n === 1) return [xs[0] - 0.5, xs[0] + 0.5];
    const out = [xs[0] - (xs[1] - xs[0]) / 2];
    for (let i = 0; i < n - 1; i++) out.push((xs[i] + xs[i + 1]) / 2);
    out.push(xs[n - 1] + (xs[n - 1] - xs[n - 2]) / 2);
    return out;
  }
  /* counts as asked: a share in percent, or a density whose area is 1; cumulatively, a density reads as the
     proportion so far, which is what the integral of a density is */
  function shapeCounts(counts, edges, { normalize = "count", cumulative = false } = {}) {
    const total = counts.reduce((a, b) => a + b, 0) || 1;
    let run = 0;
    return counts.map((c, i) => {
      if (cumulative) {
        run += c;
        return normalize === "percent" ? run / total * 100 : normalize === "density" ? run / total : run;
      }
      return normalize === "percent" ? c / total * 100 : normalize === "density" ? c / (total * (edges[i + 1] - edges[i])) : c;
    });
  }

  /* several series stacked in each bin: a percent is each one's share of its bin, so a stack reads 100; a density is
     over all the values, so the stack's area is 1; a count is a count. Cumulative counts run first, and are then shared */
  function shapeStacked(rows, edges, { normalize = "count", cumulative = false } = {}) {
    const running = rows.map((counts) => { let run = 0; return counts.map((c) => { run += c; return run; }); });
    const used = cumulative ? running : rows;
    const grand = rows.reduce((a, r) => a + r.reduce((x, y) => x + y, 0), 0) || 1;
    return used.map((counts) => counts.map((c, i) => {
      if (normalize === "percent") {
        const bin = used.reduce((a, r) => a + r[i], 0);
        return bin ? c / bin * 100 : 0;
      }
      if (normalize === "density") return cumulative ? c / grand : c / (grand * (edges[i + 1] - edges[i]));
      return c;
    }));
  }

  function linearFit(xs, ys) {
    let n = 0, sx = 0, sy = 0, sxx = 0, sxy = 0, syy = 0;
    xs.forEach((x, i) => {
      const y = ys[i];
      if (x == null || y == null || !Number.isFinite(x) || !Number.isFinite(y)) return;
      n++; sx += x; sy += y; sxx += x * x; sxy += x * y; syy += y * y;
    });
    const d = n * sxx - sx * sx;
    if (n < 2 || d === 0) return null;
    const slope = (n * sxy - sx * sy) / d, intercept = (sy - slope * sx) / n;
    const vy = n * syy - sy * sy;
    return { n, slope, intercept, r2: vy > 0 ? (n * sxy - sx * sy) ** 2 / (d * vy) : 1 };
  }

  /* a Gaussian kernel density with Silverman's bandwidth, cut at the data's range so it claims no values never seen */
  function density(values, points = 48) {
    const xs = ascending(values);
    if (xs.length < 2 || xs[0] === xs[xs.length - 1]) return null;
    const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
    const sd = Math.sqrt(xs.reduce((a, v) => a + (v - mean) ** 2, 0) / (xs.length - 1));
    const iqr = quantile(xs, 0.75) - quantile(xs, 0.25);
    const spread = iqr > 0 ? Math.min(sd, iqr / 1.34) : sd;
    const bw = 0.9 * spread * xs.length ** -0.2;
    const lo = xs[0], hi = xs[xs.length - 1];
    const at = Array.from({ length: points }, (_, i) => lo + (hi - lo) * i / (points - 1));
    const norm = 1 / (xs.length * bw * Math.sqrt(2 * Math.PI));
    return { at, values: at.map((x) => norm * xs.reduce((a, v) => a + Math.exp(-0.5 * ((x - v) / bw) ** 2), 0)) };
  }

  /* phase carried across +-180 degrees. An unreliable point is placed near the last reliable one and never becomes
     the reference, so noise at one frequency cannot shift every phase after it by a turn */
  function unwrapPhase(deg, reliable = () => true) {
    const out = new Array(deg.length).fill(null);
    let ref = null;
    deg.forEach((d, i) => {
      if (d == null || !Number.isFinite(d)) return;
      const v = ref == null ? d : d + 360 * Math.round((ref - d) / 360);
      out[i] = v;
      if (reliable(i) || ref == null) ref = v;
    });
    return out;
  }
  const wrapPhase = (d) => { if (d == null) return null; const w = ((d % 360) + 360) % 360; return w > 180 ? w - 360 : w; };

  function niceStep(span, count, steps = null) {
    const rough = span / Math.max(1, count);
    if (steps) return steps.find((s) => s >= rough) ?? steps[steps.length - 1];
    const mag = 10 ** Math.floor(Math.log10(rough)), f = rough / mag;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * mag;
  }
  function linearTicks(lo, hi, count, steps = null) {
    if (!(hi > lo)) return [lo];
    const step = niceStep(hi - lo, count, steps), out = [];
    for (let k = Math.ceil(lo / step - 1e-9); k * step <= hi + step * 1e-9; k++) out.push(+(k * step).toPrecision(12));
    return out;
  }
  /* decades as the major ticks, and 2 to 9 of each as the minor ones */
  function logTicks(lo, hi) {
    const major = [], minor = [];
    for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) {
      const v = 10 ** e;
      if (v >= lo * 0.9999 && v <= hi * 1.0001) major.push(v);
      for (let m = 2; m <= 9; m++) { const w = m * v; if (w >= lo && w <= hi) minor.push(w); }
    }
    return { major, minor };
  }

  return { finite, ascending, quantile, boxStats, boxFrom, autoBins, edgesOver, countInto, edgesFromX, shapeCounts, shapeStacked, linearFit, density,
           unwrapPhase, wrapPhase, niceStep, linearTicks, logTicks };
})();
