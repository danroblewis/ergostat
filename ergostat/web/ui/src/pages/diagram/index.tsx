import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { Async, Fields, Menu, Segmented, Tabs, useDetail } from "../../components";
import { DiagramCanvas, graphOf, usePartPanels, type Acts, type ViewKey } from "../../components/diagram";
import { useApi } from "../../hooks/useApi";
import { useStatus } from "../../state/status";
import { Side } from "./Side";

/* The Diagram page (diagram.js's pageDiagram): one control system, drawn three ways (Dynamics, Blocks, Process), the
   view and what is drawn in the address (?view=, system=, open=, around=, item=, kind=; the Process view's kinds=,
   by=, paths=, show=), asked again every 2.5 s; a click opens a part's panel, the side lists what needs the owner.
   The drawing is components/diagram's DiagramCanvas, as on any page; this page adds the toolbar, the side and the
   address. */

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
  const g = graphOf(view, st.data);

  const toggleSystem = useCallback((name: string) => {
    const now = new Set<string>(g?.open || []);
    if (now.has(name)) { now.delete(name); for (const [k, v] of Object.entries<any>(g?.tree || {})) if (v.within === name) now.delete(k); }
    else now.add(name);
    go({ open: [...now].join(",") || "-" });
  }, [g, go]);
  const drill = useCallback((name: string) => go({ system: name, open: "", around: "", item: "", kind: "" }), [go]);
  const sysActs = useMemo(() => ({ toggleSystem, drill }), [toggleSystem, drill]);
  const pick = usePartPanels(g, view, sysActs);
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

  return (
    <div className="diagram">
      <DiagramCanvas g={g} view={view} show={show} acts={acts} scope={`${view}|${system}|${around}|${item}|${kind}`}
        labelledBy="diagram-caption" file={file} onBackground={detail.close}
        waiting={st.error ? <>The server is not answering. Is ergostat still running? ({st.error.message})</> : "Loading…"}>
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
              <Segmented label="Nodes" value={q.get("by") || g?.by || ""} onChange={(b) => go({ by: b })}
                options={[{ value: "states", label: "States" }, { value: "events", label: "Events" }]} />
              <span className="sep" />
              <Segmented label="Numbers" value={show === "times" ? "times" : ""} onChange={(v) => go({ show: v })}
                options={[{ value: "", label: "Counts" }, { value: "times", label: "Times" }]} />
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
      </DiagramCanvas>
      <aside className="side" aria-label="About the diagram">
        <Side g={g} view={view} onGoal={onGoal} onPick={pick} />
      </aside>
    </div>
  );
}
