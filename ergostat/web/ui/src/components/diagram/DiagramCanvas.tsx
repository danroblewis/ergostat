import { useEffect, useRef, type ReactNode } from "react";
import { BlocksDrawing } from "./Blocks";
import { DynamicsDrawing, type Acts } from "./Dynamics";
import { ProcessDrawing } from "./Process";
import { usePanZoom } from "./usePanZoom";
import { boundsOf, emptyText, useDiagramLayout, type ViewKey } from "./useLayout";

/* A graph from /api/graph drawn in one of the three views, on a canvas that pans and zooms, with Fit, zoom and Export
   SVG at its foot. What it is placed in sizes it (.canvas-wrap fills its parent). ``children`` are drawn over it: the
   Diagram page's toolbar, say. ``scope`` names what is drawn: a new scope is shown whole, the same scope laid out
   again keeps where the reader moved it. */

export interface DiagramCanvasProps {
  g: any | undefined;
  view: ViewKey;
  acts: Acts;
  /** the Process view's numbers: "" counts, "times" times */
  show?: string;
  scope: string;
  /** the id of the element that names the drawing (its caption) */
  labelledBy?: string;
  /** Export SVG's file name; none: no export */
  file?: string;
  /** room left at the top for what is drawn over the canvas, when fitting */
  fitTop?: number;
  /** said over the canvas when there is no graph yet: "Loading…", or why not */
  waiting?: ReactNode;
  onBackground?: () => void;
  className?: string;
  children?: ReactNode;
}

export function exportSvg(svg: SVGSVGElement | null, file: string) {
  if (!svg) return;
  const copy = svg.cloneNode(true) as SVGSVGElement;
  const b = svg.querySelector<SVGGElement>(".viewport")?.getBBox();
  copy.querySelector(".viewport")?.removeAttribute("transform");
  if (b) copy.setAttribute("viewBox", `${b.x - 14} ${b.y - 14} ${b.width + 28} ${b.height + 28}`);
  copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const css = [...document.styleSheets].flatMap((s) => { try { return [...s.cssRules].map((r) => r.cssText); } catch { return []; } }).join("\n");
  const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
  style.textContent = css;
  copy.prepend(style);
  const url = URL.createObjectURL(new Blob([copy.outerHTML], { type: "image/svg+xml" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: file });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function DiagramCanvas({ g, view, acts, show = "", scope, labelledBy, file, fitTop = 80, waiting, onBackground, className, children }: DiagramCanvasProps) {
  const { lay, key, error } = useDiagramLayout(g, view, show);
  const svgRef = useRef<SVGSVGElement>(null);
  const pz = usePanZoom(svgRef);
  const fittedFor = useRef("");
  useEffect(() => {
    if (!lay) return;
    if (fittedFor.current !== scope || !pz.moved.current) {
      pz.fit(boundsOf(lay), fitTop);
      fittedFor.current = scope;
    }
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const empty = emptyText(g, view);

  return (
    <div className={`canvas-wrap${className ? ` ${className}` : ""}`}>
      <svg ref={svgRef} className={`canvas${view === "dynamics" ? " sd" : view === "blocks" ? " bd" : ""}`} aria-labelledby={labelledBy} {...pz.handlers}
        onClick={(ev) => { if (ev.target === ev.currentTarget) onBackground?.(); }}>
        <g className="viewport" transform={`translate(${pz.view.x},${pz.view.y}) scale(${pz.view.k})`}>
          {lay && g && !empty && (view === "blocks" ? <BlocksDrawing g={g} lay={lay} acts={acts} />
            : view === "process" ? <ProcessDrawing g={g} lay={lay} acts={acts} show={show} />
              : <DynamicsDrawing g={g} lay={lay} acts={acts} />)}
        </g>
      </svg>
      {children}
      <div className="zoom">
        <button type="button" className="z" title="Zoom out" aria-label="Zoom out" onClick={() => pz.zoomBy(1 / 1.2)}>−</button>
        <button type="button" title="Show it whole" onClick={() => pz.fit(boundsOf(lay), fitTop)}>Fit</button>
        <button type="button" className="z" title="Zoom in" aria-label="Zoom in" onClick={() => pz.zoomBy(1.2)}>+</button>
        {file && (
          <>
            <span className="sep" />
            <button type="button" title="Save the diagram as an SVG file" onClick={() => exportSvg(svgRef.current, file)}>Export SVG</button>
          </>
        )}
      </div>
      {!g && waiting && <div className="empty">{waiting}</div>}
      {empty && <div className="empty">{empty}</div>}
      {error && <div className="empty">The layout failed: {error}</div>}
    </div>
  );
}
