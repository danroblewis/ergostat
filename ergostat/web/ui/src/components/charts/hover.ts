import type uPlot from "uplot";
import { stamp } from "../../lib/format";

/* A chart's hover readout (a uPlot plugin): at the cursor, the time and each line shown with its colour, name and value,
   so a chart needs no legend. Built with text nodes only (a series' name is the model's, never markup). */

const colourOf = (u: uPlot, i: number): string => {
  const s: any = u.series[i];
  const c = typeof s.stroke === "function" ? s.stroke(u, i) : s.stroke;
  return typeof c === "string" ? c : "currentColor";
};

export function hoverPlugin(text: (v: number | null, i: number, idx: number) => string = (v) => (v == null ? "–" : String(+v.toPrecision(4)))): uPlot.Plugin {
  let tip: HTMLDivElement;
  const hide = () => { if (tip) tip.hidden = true; };
  return {
    hooks: {
      init: (u: uPlot) => {
        tip = document.createElement("div");
        tip.className = "chart-tip";
        tip.hidden = true;
        u.over.appendChild(tip);
        u.over.addEventListener("mouseleave", hide);
      },
      setCursor: (u: uPlot) => {
        const { idx, left, top } = u.cursor;
        if (idx == null || left == null || left < 0 || !tip) return hide();
        tip.replaceChildren();
        const head = document.createElement("div");
        head.className = "chart-tip-time";
        head.textContent = stamp(Number(u.data[0][idx]));
        tip.appendChild(head);
        for (let i = 1; i < u.series.length; i++) {
          const s = u.series[i];
          if (s.show === false) continue;
          const row = document.createElement("div");
          const sw = document.createElement("span");
          sw.className = "chart-tip-swatch";
          sw.style.background = colourOf(u, i);
          const name = document.createElement("span");
          name.textContent = ` ${s.label ?? ""} `;
          const val = document.createElement("b");
          val.textContent = text((u.data[i] as (number | null)[])[idx] ?? null, i, idx);
          row.append(sw, name, val);
          tip.appendChild(row);
        }
        tip.hidden = false;
        const w = u.over.clientWidth, h = u.over.clientHeight;
        const tw = tip.offsetWidth, th = tip.offsetHeight;
        tip.style.left = `${left + 12 + tw > w ? Math.max(0, left - 12 - tw) : left + 12}px`;
        tip.style.top = `${Math.max(0, Math.min((top ?? 0) - th / 2, h - th))}px`;
      },
    },
  };
}
