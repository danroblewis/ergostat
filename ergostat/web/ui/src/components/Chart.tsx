import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

/* A time series chart (uPlot): ``times`` in epoch seconds, each series its values at those times (null: no reading).
   It fills its box's width and redraws on resize; the options are built by the caller for anything beyond a line. */

export interface Series {
  label: string;
  values: (number | null)[];
  stroke?: string;
  dash?: number[];
  fill?: string;
}

interface ChartProps {
  times: number[];
  series: Series[];
  height?: number;
  title?: string;
  /** Extra uPlot options, merged over the defaults (axes, scales, hooks). */
  options?: Partial<uPlot.Options>;
  className?: string;
}

const PALETTE = ["var(--c1, #3b6fd4)", "var(--c2, #d4823b)", "var(--c3, #3ba86b)", "var(--c4, #a03bd4)", "var(--c5, #d43b5c)"];
const colour = (i: number) => {
  const css = getComputedStyle(document.documentElement);
  const named = css.getPropertyValue(`--c${i + 1}`).trim();
  return named || ["#3b6fd4", "#d4823b", "#3ba86b", "#a03bd4", "#d43b5c"][i % 5];
};

export function Chart({ times, series, height = 180, title, options, className }: ChartProps) {
  const box = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const opts: uPlot.Options = {
      width: el.clientWidth || 400,
      height,
      title,
      legend: { show: series.length > 1 },
      series: [{}, ...series.map((s, i) => ({ label: s.label, stroke: s.stroke ?? colour(i), dash: s.dash, fill: s.fill, width: 1.5, spanGaps: false }))],
      axes: [{}, { size: 50 }],
      ...options,
    };
    const data = [times, ...series.map((s) => s.values)] as uPlot.AlignedData;
    plot.current = new uPlot(opts, data, el);
    const ro = new ResizeObserver(() => plot.current?.setSize({ width: el.clientWidth, height }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      plot.current?.destroy();
      plot.current = null;
    };
    // a new chart when its shape changes; new data alone is set in place (below)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series.length, height, title, options]);

  useEffect(() => {
    plot.current?.setData([times, ...series.map((s) => s.values)] as uPlot.AlignedData);
  }, [times, series]);

  return <div ref={box} className={`chart ${className ?? ""}`.trim()} />;
}

export { PALETTE };
