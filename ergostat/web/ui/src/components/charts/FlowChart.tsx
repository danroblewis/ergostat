import { useMemo } from "react";
import { Chart, type Series } from "./Chart";

const STATE_COLOURS = ["#3b6fd4", "#d4823b", "#3ba86b", "#a03bd4", "#d43b5c", "#2fa3a3", "#8a8a2f", "#7a5c3b"];
const GROUP_COLOURS: Record<string, string> = { waiting: "#d4823b", working: "#3b6fd4", stopped: "#d43b5c", done: "#3ba86b" };

/** States stacked over the window (a cumulative flow diagram): each state's count at each time, the first on top. */
export function FlowChart({ times, states, counts, height = 120, xAxis = true }: {
  times: number[]; states: string[]; counts: Record<string, number[]>; height?: number; xAxis?: boolean;
}) {
  const series: Series[] = useMemo(() => {
    const shown = states.filter((s) => counts[s]);
    // stacked: each series the sum of itself and those drawn under it (the last state at the bottom)
    const acc = times.map(() => 0);
    const out: Series[] = [];
    for (let i = shown.length - 1; i >= 0; i--) {
      const s = shown[i], c = counts[s];
      for (let j = 0; j < acc.length; j++) acc[j] += c[j] || 0;
      const colour = GROUP_COLOURS[s] || STATE_COLOURS[i % STATE_COLOURS.length];
      out.unshift({ label: s, values: [...acc], stroke: colour, fill: colour + "55" });
    }
    return out;
  }, [times, states, counts]);
  const options = useMemo(() => (xAxis ? undefined : { axes: [{ show: false }, { size: 36 }] }), [xAxis]);
  if (!series.length) return null;
  return <Chart times={times} series={series} height={height} options={options} className="flow-chart" />;
}
