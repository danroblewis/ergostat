import { useEffect, useState } from "react";
import type uPlot from "uplot";

/* Charts in the page's theme. uPlot draws its axes, ticks and grid on a canvas, where CSS does not reach: their colours
   are read here from the page's tokens (--muted, --line, styles/style.css), light or dark, and a chart is drawn again
   when the theme changes (useScheme). */

const DARK = "(prefers-color-scheme: dark)";

/** The page's colour scheme now, following the system's as the stylesheet does. */
export function useScheme(): "light" | "dark" {
  const query = typeof window !== "undefined" && window.matchMedia ? window.matchMedia(DARK) : null;
  const [dark, setDark] = useState(() => !!query?.matches);
  useEffect(() => {
    if (!query) return;
    const on = (e: MediaQueryListEvent) => setDark(e.matches);
    query.addEventListener("change", on);
    return () => query.removeEventListener("change", on);
  }, [query]);
  return dark ? "dark" : "light";
}

const token = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

/** One axis in the theme's colours: its labels secondary text, its grid and ticks hairlines. */
export function themedAxis(axis: uPlot.Axis = {}): uPlot.Axis {
  const text = token("--muted", "#666d74"), line = token("--line", "#dee2e6");
  return {
    stroke: text,
    grid: { stroke: line, width: 1 },
    ticks: { stroke: line, width: 1 },
    border: { show: false },
    ...axis,
  };
}

/** A chart's two axes (time, then value) in the theme, each over what the caller sets. */
export const themedAxes = (x: uPlot.Axis = {}, y: uPlot.Axis = {}): uPlot.Axis[] => [themedAxis(x), themedAxis(y)];
