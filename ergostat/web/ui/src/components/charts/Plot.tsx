import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { dur, fmt } from "../../lib/format";

/* A panel's plot over time (uPlot), filling its box in both directions (the shared Chart takes a fixed height):
   lines, areas, areas stacked, steps and bars, its Y axis in the panel's unit. */

export interface PlotSeries { label: string; values: (number | null)[] }
export interface PlotProps {
  times: number[];
  series: PlotSeries[];
  kind: "line" | "bar";
  fill?: boolean;
  stacked?: boolean;
  step?: boolean;
  unit?: string;
  yMin?: number;
  legend?: boolean;
}

const FALLBACK = ["#3b6fd4", "#d4823b", "#3ba86b", "#a03bd4", "#d43b5c", "#2a9db0", "#8a8a2a", "#b04a8a"];
function colour(i: number): string {
  const css = getComputedStyle(document.documentElement);
  return css.getPropertyValue(`--c${(i % 8) + 1}`).trim() || FALLBACK[i % FALLBACK.length];
}
const alpha = (c: string, a: number) => (/^#[0-9a-f]{6}$/i.test(c) ? c + Math.round(a * 255).toString(16).padStart(2, "0") : c);

export const valueText = (v: number | null | undefined, unit = ""): string =>
  v == null ? "–" : unit === "s" ? dur(v) : `${fmt(v)}${unit ? (unit.startsWith("/") ? "" : " ") + unit : ""}`;

/** Each series added to those before it, so the areas stack. */
function stack(series: PlotSeries[]): PlotSeries[] {
  let acc: (number | null)[] = [];
  return series.map((s) => {
    acc = s.values.map((v, i) => (v == null && acc[i] == null ? null : (v ?? 0) + (acc[i] ?? 0)));
    return { label: s.label, values: acc };
  });
}

export function Plot({ times, series, kind, fill, stacked, step, unit = "", yMin, legend }: PlotProps) {
  const box = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const shown = stacked ? stack(series) : series;
  const shape = JSON.stringify([series.map((s) => s.label), kind, fill, stacked, step, unit, yMin, legend]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const bars = kind === "bar" ? uPlot.paths.bars!({ size: [0.8, 40], align: stacked ? 0 : 0 }) : undefined;
    const stepped = step ? uPlot.paths.stepped!({ align: 1 }) : undefined;
    const opts: uPlot.Options = {
      width: Math.max(80, el.clientWidth),
      height: Math.max(60, el.clientHeight),
      legend: { show: !!legend },
      cursor: { drag: { x: false, y: false } },
      scales: { y: yMin != null ? { range: (_u, lo, hi) => [Math.min(yMin, lo ?? 0), hi == null || hi <= yMin ? yMin + 1 : hi * 1.05] } : {} },
      series: [
        {},
        ...series.map((s, i) => {
          const c = colour(i);
          return {
            label: s.label, stroke: c, width: kind === "bar" ? 0 : 1.5, spanGaps: false,
            fill: kind === "bar" ? alpha(c, 0.8) : fill || stacked ? alpha(c, 0.25) : undefined,
            paths: bars || stepped, points: { show: kind !== "bar" && s.values.filter((v) => v != null).length < 40, size: 4 },
            value: (_u: uPlot, v: number | null) => valueText(v, unit),
          };
        }),
      ],
      axes: [{}, { size: 76, values: (_u, vals) => vals.map((v) => valueText(v, unit)) }],
    };
    // later series drawn first, so a stacked area's lower bands lie over the upper ones
    const order = stacked ? [...shown].reverse() : shown;
    if (stacked) opts.series = [opts.series[0], ...opts.series.slice(1).reverse()];
    plot.current = new uPlot(opts, [times, ...order.map((s) => s.values)] as uPlot.AlignedData, el);
    const ro = new ResizeObserver(() => plot.current?.setSize({ width: Math.max(80, el.clientWidth), height: Math.max(60, el.clientHeight) }));
    ro.observe(el);
    return () => { ro.disconnect(); plot.current?.destroy(); plot.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shape]);

  useEffect(() => {
    const order = stacked ? [...shown].reverse() : shown;
    plot.current?.setData([times, ...order.map((s) => s.values)] as uPlot.AlignedData);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [times, series]);

  return <div ref={box} className="panel-plot" style={{ position: "relative", overflow: "hidden" }} />;
}
