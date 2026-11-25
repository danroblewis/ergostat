import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

/* Pan and zoom over an svg (interact.js's panZoom, without the marquee, the drags of parts and the edge hint):
   the wheel zooms about the pointer (with Ctrl or a pinch, or always), a drag on the background pans, Fit shows it all.
   ``moved`` says the view was moved by hand, so a refresh does not fit again. */
export interface View { x: number; y: number; k: number }

export function usePanZoom(svgRef: RefObject<SVGSVGElement | null>) {
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 1 });
  const drag = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null);
  const moved = useRef(false);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const wheel = (ev: WheelEvent) => {
      ev.preventDefault();
      const r = svg.getBoundingClientRect();
      const px = ev.clientX - r.left, py = ev.clientY - r.top;
      const f = Math.exp(-ev.deltaY * (ev.ctrlKey ? 0.01 : 0.0015));
      moved.current = true;
      setView((v) => {
        const k = Math.min(8, Math.max(0.05, v.k * f));
        return { k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k };
      });
    };
    svg.addEventListener("wheel", wheel, { passive: false });
    return () => svg.removeEventListener("wheel", wheel);
  }, [svgRef]);

  const onPointerDown = useCallback((ev: React.PointerEvent<SVGSVGElement>) => {
    if (ev.button !== 0 || (ev.target as Element).closest(".node, .edge, .sys-btn, .hull text")) return;
    setView((v) => { drag.current = { x: ev.clientX, y: ev.clientY, vx: v.x, vy: v.y, moved: false }; return v; });
    (ev.currentTarget as Element).setPointerCapture?.(ev.pointerId);
  }, []);
  const onPointerMove = useCallback((ev: React.PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d) return;
    const dx = ev.clientX - d.x, dy = ev.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < 3) return;
    d.moved = true; moved.current = true;
    setView((v) => ({ ...v, x: d.vx + dx, y: d.vy + dy }));
  }, []);
  const onPointerUp = useCallback(() => { drag.current = null; }, []);

  /** Show the box ``b`` whole, centred (at most at full size). */
  const fit = useCallback((b: { x: number; y: number; width: number; height: number } | null, top = 80) => {
    const svg = svgRef.current;
    if (!svg || !b) return;
    const r = svg.getBoundingClientRect();
    const W = r.width - 40, H = r.height - top - 60;
    const k = Math.min(1, W / Math.max(b.width, 1), H / Math.max(b.height, 1));
    moved.current = false;
    setView({ k, x: 20 + (W - b.width * k) / 2 - b.x * k, y: top + (H - b.height * k) / 2 - b.y * k });
  }, [svgRef]);

  const zoomBy = useCallback((f: number) => {
    const svg = svgRef.current;
    const r = svg?.getBoundingClientRect();
    const px = (r?.width || 0) / 2, py = (r?.height || 0) / 2;
    moved.current = true;
    setView((v) => { const k = v.k * f; return { k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k }; });
  }, [svgRef]);

  return { view, fit, zoomBy, moved, handlers: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel: onPointerUp } };
}
