import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Async, Fields, Menu, Tabs, useDetail } from "../../components";
import { useApi } from "../../hooks/useApi";
import { useStatus } from "../../state/status";
import { BlocksDrawing } from "./Blocks";
import { DynamicsDrawing, type Acts } from "./Dynamics";
import { layoutBlocks, layoutDynamics, layoutProcess, structureKey, type Layout } from "./lib/layout";
import { BlockPanel, ProcessPanel, SdPartPanel, SystemPanel } from "./PartDetail";
import { pmLabel, ProcessDrawing } from "./Process";
import { Side } from "./Side";
import { usePanZoom } from "./usePanZoom";
import "./diagram.css";

/* The Diagram page (diagram.js's pageDiagram): one control system, drawn three ways (Dynamics, Blocks, Process), the
   view and what is drawn in the address (?view=, system=, open=, around=, item=, kind=; the Process view's kinds=,
   by=, paths=, show=), asked again every 2.5 s; a click opens a part's panel, the side lists what needs the owner. */

type ViewKey = "dynamics" | "blocks" | "process";
const VIEWS: { key: ViewKey; label: React.ReactNode; title: string }[] = [
  { key: "dynamics", label: <>Dynamics<span className="what"> · what is</span></>, title: "The stock-and-flow diagram, as system dynamics draws it" },
  { key: "blocks", label: <>Blocks<span className="what"> · what is controlled</span></>, title: "The control system as a block diagram" },
  { key: "process", label: <>Process<span className="what"> · what happened</span></>, title: "The process map: how items really moved, from the record" },
];
const KEEP = ["view", "system", "around", "open", "item", "kind", "kinds", "by", "paths", "show", "window", "at"];

function GoalPanel({ name }: { name: string }) {
  const st = useApi<any>(`loops/${encodeURIComponent(name)}`);
  return (
    <>
      <div className="kind">Goal</div>
      <h2>{name}</h2>
      <Async state={st}>
        {(lp) => (
          <Fields caption="The goal" fields={[
            ["state", lp.status ?? lp.state], ["measure", lp.row?.measure ?? lp.stock], ["setpoint", lp.setpoint],
            ["now", lp.row?.value ?? lp.value], ["off by", lp.off_by_words], ["description", lp.description],
          ].filter(([, v]) => v != null && v !== "") as [string, any][]} />
        )}
      </Async>
    </>
  );
}

function exportSvg(svg: SVGSVGElement | null, file: string) {
  if (!svg) return;
  const copy = svg.cloneNode(true) as SVGSVGElement;
  const vp = svg.querySelector<SVGGElement>("#viewport");
  const b = vp?.getBBox();
  copy.querySelector("#viewport")?.removeAttribute("transform");
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

export default function DiagramPage() {
  const [q, setQ] = useSearchParams();
  const raw = q.get("view");
  const view: ViewKey = raw === "blocks" || raw === "process" ? raw : "dynamics";
  const system = q.get("system") || "", around = q.get("around") || "";
  const item = view !== "process" ? q.get("item") || "" : "", kind = view !== "process" && !item ? q.get("kind") || "" : "";
  const open = q.get("open");
  const show = q.get("show") || "";
  const { status } = useStatus();
  const detail = useDetail();

  const go = useCallback((over: Record<string, string>) => {
    setQ((p) => {
      const n = new URLSearchParams();
      for (const k of KEEP) { const v = p.get(k); if (v) n.set(k, v); }
      for (const [k, v] of Object.entries(over)) { if (v) n.set(k, v); else n.delete(k); }
      if (n.get("view") === "dynamics") n.delete("view");
      return n;
    });
  }, [setQ]);

  const params = {
    view, system, around, item, kind,
    ...(open != null && view !== "process" ? { open } : {}),
    ...(view === "process" ? { kinds: q.get("kinds") || "", by: q.get("by") || "", paths: q.get("paths") || "" } : {}),
  };
  const st = useApi<any>("graph", params, { every: 2500 });
  const g = st.data && st.data.kind && (view === "process" ? st.data.kind === "process" : view === "blocks" ? st.data.kind === "blocks" : st.data.kind !== "process" && st.data.kind !== "blocks") ? st.data : undefined;

  // the layout: made again only when the structure changes; new values are drawn where the parts already are
  const key = useMemo(() => (g ? structureKey(g) + (view === "process" ? JSON.stringify([show, g.nodes.map((n: any) => n.count)]) : "") : ""), [g, view, show]);
  const [laid, setLaid] = useState<{ key: string; lay: Layout } | null>(null);
  const [layErr, setLayErr] = useState<string | null>(null);
  useEffect(() => {
    if (!g || !key || laid?.key === key) return;
    let gone = false;
    const run = view === "blocks" ? layoutBlocks(g) : view === "process" ? layoutProcess(g, (e) => pmLabel(e, show)) : layoutDynamics(g);
    run.then((lay) => { if (!gone) { setLaid({ key, lay }); setLayErr(null); } })
      .catch((e) => { if (!gone) setLayErr(String(e?.message || e)); });
    return () => { gone = true; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const svgRef = useRef<SVGSVGElement>(null);
  const pz = usePanZoom(svgRef);
  const fittedFor = useRef("");
  const lay = laid && g ? laid.lay : null;
  useEffect(() => {
    if (!lay || !laid) return;
    // a new view or system: shown whole; the same one laid out again keeps what the reader moved
    const scope = `${view}|${system}|${around}|${item}|${kind}`;
    if (fittedFor.current !== scope || !pz.moved.current) {
      const xs = [...lay.children, ...lay.hulls];
      const x0 = Math.min(...xs.map((c) => c.x)), y0 = Math.min(...xs.map((c) => c.y));
      const x1 = Math.max(...xs.map((c) => c.x + c.width)), y1 = Math.max(...xs.map((c) => c.y + c.height + 30));
      pz.fit(xs.length ? { x: x0, y: y0, width: x1 - x0, height: y1 - y0 } : null);
      fittedFor.current = scope;
    }
  }, [laid?.key]); // eslint-disable-line react-hooks/exhaustive-deps
  const fitNow = () => {
    if (!lay) return;
    const xs = [...lay.children, ...lay.hulls];
    if (!xs.length) return;
    const x0 = Math.min(...xs.map((c) => c.x)), y0 = Math.min(...xs.map((c) => c.y));
    pz.fit({ x: x0, y: y0, width: Math.max(...xs.map((c) => c.x + c.width)) - x0, height: Math.max(...xs.map((c) => c.y + c.height + 30)) - y0 });
  };

  const toggleSystem = useCallback((name: string) => {
    const now = new Set<string>(g?.open || []);
    if (now.has(name)) { now.delete(name); for (const [k, v] of Object.entries<any>(g?.tree || {})) if (v.within === name) now.delete(k); }
    else now.add(name);
    go({ open: [...now].join(",") || "-" });
  }, [g, go]);
  const drill = useCallback((name: string) => go({ system: name, open: "", around: "", item: "", kind: "" }), [go]);
  const sysActs = { toggleSystem, drill };

  const pick = useCallback((n: any) => {
    if (!g) return;
    const k = n.id;
    if (view === "process") detail.open(k, <ProcessPanel n={n} g={g} />);
    else if (view === "blocks") detail.open(k, <BlockPanel n={n} acts={sysActs} />);
    else if (n.kind === "system") detail.open(k, <SystemPanel n={n} acts={sysActs} />);
    else detail.open(k, <SdPartPanel n={n} g={g} />);
  }, [g, view, detail]); // eslint-disable-line react-hooks/exhaustive-deps
  const onGoal = useCallback((name: string) => detail.open(`goal:${name}`, <GoalPanel name={name} />), [detail]);
  const acts: Acts = { pick, toggleSystem, drill, sel: detail.key };

  // the system picker as the tree it is: each system under the one it is within
  const tree: Record<string, any> = g?.tree || {};
  const sysOptions = useMemo(() => {
    const out: { value: string; label: string }[] = [{ value: "", label: "Everything" }];
    const names = Object.keys(tree).length ? null : (status?.systems || []);
    if (names) return [...out, ...names.map((x: string) => ({ value: x, label: x }))];
    const add = (p: string | null, depth: number) => {
      for (const x of Object.keys(tree).filter((k) => (tree[k].within || null) === p).sort()) { out.push({ value: x, label: "  ".repeat(depth) + x }); add(x, depth + 1); }
    };
    add(null, 0);
    return out;
  }, [JSON.stringify(tree), status?.systems]); // eslint-disable-line react-hooks/exhaustive-deps
  const crumbs: string[] = [];
  for (let x: string | undefined = system; x; x = tree[x]?.within) crumbs.unshift(x);

  const caption = `${view === "dynamics" ? "Stock-and-flow diagram (system dynamics)" : view === "blocks" ? "Block diagram (control)" : "Process map (from the record)"} · ${status?.name || ""}${system ? ` · ${system}` : ""}`;
  const file = `${status?.name || "ergostat"}-${system || "all"}-${view}.svg`;
  const empty = !g ? null : !g.nodes.length
    ? view === "process"
      ? (g.kinds || []).length ? `Nothing on the record in the window for ${g.kinds.map((k: any) => k.name).join(", ")}.` : "No kinds of item here: its parts are counted by sensors."
      : g.subset ? `${g.subset.says}.` : view === "blocks" ? "No control system here: no goal, and no block that acts." : "Nothing to draw: the model is empty."
    : null;

  return (
    <div className="diagram">
      <div className="canvas-wrap">
        <svg ref={svgRef} className={`canvas${view === "dynamics" ? " sd" : view === "blocks" ? " bd" : ""}`} aria-labelledby="diagram-caption" {...pz.handlers}
          onClick={(ev) => { if (ev.target === ev.currentTarget) detail.close(); }}>
          <g id="viewport" transform={`translate(${pz.view.x},${pz.view.y}) scale(${pz.view.k})`}>
            {lay && g && !empty && (view === "blocks" ? <BlocksDrawing g={g} lay={lay} acts={acts} />
              : view === "process" ? <ProcessDrawing g={g} lay={lay} acts={acts} show={show} />
                : <DynamicsDrawing g={g} lay={lay} acts={acts} />)}
          </g>
        </svg>
        <div className="toolbar">
          <Tabs label="View" tabs={VIEWS} value={view} onChange={(v) => go({ view: v })} />
          <span className="sep" />
          <select title="The system drawn" aria-label="System" value={system} onChange={(ev) => go({ system: ev.target.value, around: "", item: "", kind: "", open: "" })}>
            {sysOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          {crumbs.length > 0 && (
            <span className="crumbs">
              <a href="#" onClick={(ev) => { ev.preventDefault(); drill(""); }}>Everything</a>
              {crumbs.map((x, i) => <span key={x}> › {i < crumbs.length - 1 ? <a href="#" onClick={(ev) => { ev.preventDefault(); drill(x); }}>{x}</a> : <b>{x}</b>}</span>)}
            </span>
          )}
          {view === "process" && (
            <>
              <span className="sep" />
              <span className="seg" role="group" aria-label="Nodes">
                {(["states", "events"] as const).map((b) => (
                  <button key={b} type="button" className={(q.get("by") || g?.by) === b ? "on" : ""} onClick={() => go({ by: b })}>{b === "states" ? "States" : "Events"}</button>
                ))}
              </span>
              <span className="sep" />
              <span className="seg" role="group" aria-label="Numbers">
                <button type="button" className={show !== "times" ? "on" : ""} onClick={() => go({ show: "" })}>Counts</button>
                <button type="button" className={show === "times" ? "on" : ""} onClick={() => go({ show: "times" })}>Times</button>
              </span>
              <span className="sep" />
              <input type="range" min={0} max={100} step={5} className="pm-paths" aria-label="Paths shown" defaultValue={q.get("paths") || "0"}
                title="Hide lines rarer than this share of their kind's most frequent"
                onMouseUp={(ev) => go({ paths: (ev.target as HTMLInputElement).value === "0" ? "" : (ev.target as HTMLInputElement).value })} />
              <span className="muted small pm-paths-word">paths ≥ {q.get("paths") || 0}%</span>
            </>
          )}
          {around && <span className="around">around <b>{around}</b> <button type="button" className="ghost" aria-label="Clear" onClick={() => go({ around: "" })}>×</button></span>}
          {(item || kind) && (
            <span className="around subset">{item ? <>what <b>{item}</b> passed through </> : <>what kind <b>{kind}</b> touches </>}
              <button type="button" className="ghost" aria-label="Clear" onClick={() => go({ item: "", kind: "" })}>×</button></span>
          )}
          {view !== "process" && (
            <Menu label="⋯" className="dots" title="More: open or close every system">
              <Menu.Item onSelect={() => go({ open: "*" })}>Open all systems</Menu.Item>
              <Menu.Item onSelect={() => go({ open: "-" })}>Close all systems</Menu.Item>
            </Menu>
          )}
          <h1 id="diagram-caption" className="caption" title={caption}>{caption}</h1>
        </div>
        <div className="zoom">
          <button type="button" className="z" title="Zoom out" aria-label="Zoom out" onClick={() => pz.zoomBy(1 / 1.2)}>−</button>
          <button type="button" title="Show it whole" onClick={fitNow}>Fit</button>
          <button type="button" className="z" title="Zoom in" aria-label="Zoom in" onClick={() => pz.zoomBy(1.2)}>+</button>
          <span className="sep" />
          <button type="button" title="Save the diagram as an SVG file" onClick={() => exportSvg(svgRef.current, file)}>Export SVG</button>
        </div>
        {!g && !st.error && <div className="empty loading">Loading…</div>}
        {st.error && !g && <div className="empty">The server is not answering. Is ergostat still running? ({st.error.message})</div>}
        {empty && <div className="empty">{empty}</div>}
        {layErr && <div className="empty">The layout failed: {layErr}</div>}
      </div>
      <aside className="side" aria-label="About the diagram">
        <Side g={g} view={view} onGoal={onGoal} onPick={pick} />
      </aside>
    </div>
  );
}
