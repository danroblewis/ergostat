import type { ReactNode } from "react";
import { AppLink, Async, Chart, Fields, Rich } from "../../components";
import { useApi } from "../../hooks/useApi";
import { ago, dur, fmt, rateText } from "../../lib/format";

/* What a click on a part opens in the side panel (details.js's openNodeNow, dynamics.js's openNodeSD, blocks.js's
   openBlock, process.js's openProcessNode), each shorter than the old: no causes strip, no loop tables, no what-if. */

const MINUS = "−";
const sign = (p: string | null) => (p === "+" ? "+" : p === "-" ? MINUS : "?");
const rows = (xs: [ReactNode, ReactNode][]) => xs.filter(([, v]) => v != null && v !== "" && v !== false);

function PointsChart({ points, label }: { points: [number, number][]; label: string }) {
  if (!points || points.length < 2) return null;
  return <Chart times={points.map((p) => p[0])} series={[{ label, values: points.map((p) => p[1]) }]} height={120} />;
}

export function SystemPanel({ n, acts }: { n: any; acts: { toggleSystem: (s: string) => void; drill: (s: string) => void } }) {
  const side = (d: string) => (n.ports || []).filter((p: any) => p.side === d);
  const list = (ps: any[], none: string) => ps.length
    ? <table><tbody>{ps.map((p) => <tr key={p.id}><td>{p.label}</td><td className="muted">{p.kind}</td><td className="num">{p.value || ""}</td></tr>)}</tbody></table>
    : <p className="muted">{none}</p>;
  const loops = Object.entries(n.loops || {}).map(([k, v]) => `${v} ${k}`).join(", ");
  return (
    <>
      <div className="kind">{n.remote ? "System, remote" : "System"}</div>
      <h2>{n.label}</h2>
      {n.description && <p className="muted">{n.description}</p>}
      <Fields caption="The system" fields={rows([["loops", loops || "no loops"], ["size", n.size], ["inside", n.subsystems?.length ? n.subsystems.join(", ") : null]])} />
      {(n.charted || []).length > 0 && <p className="muted small">{n.charted.map((c: any) => `${c.label} ${c.value}`).join(" · ")}</p>}
      <h3>In, from outside</h3>
      {list(side("in"), "Nothing outside reaches in here.")}
      <h3>Out, to outside</h3>
      {list(side("out"), "Nothing outside sees it here.")}
      <div className="actions">
        <button type="button" onClick={() => acts.toggleSystem(n.label)}>Open it here</button>
        <button type="button" onClick={() => acts.drill(n.label)}>Draw it alone</button>
      </div>
      <p className="note"><code>ergostat explain system.{n.label}</code> says the same in sentences.</p>
    </>
  );
}

/** A stock, auxiliary or flow of the Dynamics view, with what /api/part/... says of it. */
export function SdPartPanel({ n, g }: { n: any; g: any }) {
  const flow = n.kind === "valve" || n.kind === "disturbance";
  const goalish = n.role === "desired" || n.role === "gap" || n.role === "decision";
  const path = goalish || n.kind === "cloud" || n.kind === "terminal" ? null
    : flow ? `part/${n.kind === "disturbance" ? "disturbance" : "flow"}/${encodeURIComponent(n.flow || n.label)}`
      : `part/stock/${encodeURIComponent(n.label)}`;
  const st = useApi<any>(path);
  const byId: Record<string, any> = Object.fromEntries(g.nodes.map((x: any) => [x.id, x]));
  const nm = (id: string) => byId[id]?.label || byId[id]?.flow || id;
  const causes = g.edges.filter((e: any) => e.kind === "connector" && e.target === n.id).map((e: any) => `${nm(e.source)} (${sign(e.polarity)})`).join(", ");
  const effects = g.edges.filter((e: any) => e.kind === "connector" && e.source === n.id).map((e: any) => `${nm(e.target)} (${sign(e.polarity)})`).join(", ");
  const loops = (g.causalLoops || []).filter((c: any) => (c.nodes || []).includes(n.id) || (c.parts || []).includes(n.id.replace(":", "."))).map((c: any) => `${c.polarity || "?"} ${c.name}`);
  const kindWord = flow ? "Valve" : n.kind === "stock" ? "Stock" : n.kind === "auxiliary" ? "Auxiliary" : n.kind === "cloud" ? "Cloud" : n.kind;
  const tail = (
    <>
      <Fields caption="Its links" fields={rows([["depends on", causes], ["drives", effects]])} />
      {loops.length > 0 && <p><b>In the loops</b> {loops.join(", ")}</p>}
      {(n.kind === "stock" || flow) && (
        <p><AppLink to={`/diagram?view=dynamics&around=${n.kind === "stock" ? "stock" : "flow"}/${encodeURIComponent(n.flow || n.label)}`}>Draw what is around it</AppLink></p>
      )}
    </>
  );
  if (!path) {
    return (
      <>
        <div className="kind">{kindWord}</div>
        <h2>{n.label || n.flow || n.id}</h2>
        <Fields caption="It" fields={rows([
          ["desired level", n.goal ? `desired ${n.of} ${n.setpoint || `= ${n.desired ?? n.valueText}`} (${n.goal})` : null],
          ["gap", n.role === "gap" ? `now ${n.offBy || n.valueText || "not known yet"}` : null],
          ["feedback", n.noFeedback ? "none: nothing in the model acts on this gap, so no loop closes it (an open loop)" : null],
          ["switching", n.switching], ["description", n.description], ["flow", n.kind === "cloud" ? n.flow : null],
        ])} />
        {tail}
      </>
    );
  }
  return (
    <>
      <div className="kind">{kindWord}</div>
      <h2>{n.flow || n.label}</h2>
      <Async state={st}>
        {(d) => {
          const m = d?.model || {}, now = d?.now || {};
          if (flow) return (
            <>
              <p className="muted">the rate of {n.flow || n.label}</p>
              <Fields caption="The flow" fields={rows([
                ["rate, over the window", now.rate !== undefined || n.rate != null ? rateText(now.rate ?? n.rate, d?.unit, n.flow) : "not measured"],
                ["how it is known", now.how || n.how], ["equation", n.equation || d?.equation], ["description", m.description || n.description],
                ["filled by", d?.agent ? <AppLink to={`/agent/${encodeURIComponent(d.agent)}`}>{d.agent}</AppLink> : null],
              ])} />
            </>
          );
          return (
            <>
              <PointsChart points={now.points} label={n.label} />
              <Fields caption="The stock" fields={rows([
                ["description", m.description || n.description], ["now", `${fmt(now.value ?? n.value)} ${m.unit || n.unit || ""}`],
                ["measured", now.at ? `${ago(now.at)}${now.sensor ? ` by its sensor ${now.sensor}` : ""}` : null],
                ["inflow", n.kind === "stock" && now.inflow != null ? rateText(now.inflow) : null],
                ["outflow", n.kind === "stock" && now.outflow != null ? rateText(now.outflow) : null],
                ...(n.goals || []).map((gl: any) => ["desired level", `desired ${n.label} ${gl.setpoint || `= ${gl.desired}`} (${gl.name})`] as [ReactNode, ReactNode]),
              ])} />
            </>
          );
        }}
      </Async>
      {tail}
    </>
  );
}

const BD_KIND: Record<string, string> = { controller: "Controller", process: "Process", sensor: "Sensor", comparator: "Comparator",
  disturbance: "Disturbance", output: "Output", reference: "Reference", subsystem: "System", collector: "Collector" };

export function BlockPanel({ n, acts }: { n: any; acts: { toggleSystem: (s: string) => void; drill: (s: string) => void } }) {
  const fn = n.fn || {};
  const title = fn.sym ? <>{fn.sym}{fn.sub && <sub>{fn.sub}</sub>}{fn.arg && `(${fn.arg})`}</> : fn.name || n.label;
  const model = (n.rows || []).filter(([, v]: any) => v != null && v !== "");
  const me = n.id?.startsWith("blk:") ? n.id.slice(4) : null;
  return (
    <>
      <div className="kind">{BD_KIND[n.role] || n.role || n.kind}</div>
      <h2>{title}</h2>
      {n.says && <p className="what"><Rich text={n.says} /></p>}
      {model.length > 0 && <><h3>In the model</h3><Fields caption="In the model" fields={model.map(([k, v]: any) => [k, typeof v === "string" ? <Rich text={v} /> : String(v)])} /></>}
      {me && <p><AppLink to={`/agent/${encodeURIComponent(me)}`}>{me}</AppLink></p>}
      {(n.loops || []).length > 0 && <><h3>In the control loop{n.loops.length > 1 ? "s" : ""} of</h3><p>{n.loops.join(", ")}</p></>}
      {n.role === "subsystem" && (
        <div className="actions">
          <button type="button" onClick={() => acts.toggleSystem(n.system || n.label)}>Open it here</button>
          <button type="button" onClick={() => acts.drill(n.system || n.label)}>Draw it alone</button>
        </div>
      )}
    </>
  );
}

export function ProcessPanel({ n, g }: { n: any; g: any }) {
  const into = g.edges.filter((e: any) => e.target === n.id && e.source !== n.id);
  const out = g.edges.filter((e: any) => e.source === n.id && e.target !== n.id);
  const act = (id: string) => g.nodes.find((x: any) => x.id === id)?.label ?? id;
  const lines = (es: any[], other: (e: any) => string) => es.length
    ? <table><tbody>{es.map((e) => (
        <tr key={e.id}><td>{act(other(e))}</td><td className="muted">{e.rework ? `rework ×${e.returns}` : e.kind !== "follows" ? e.kind : ""}</td>
          <td className="num">{e.count}</td><td className="num muted">{e.median != null ? dur(e.median) : ""}</td></tr>))}</tbody></table>
    : <p className="muted">None in the window.</p>;
  return (
    <>
      <div className="kind">{n.kind === "activity" ? (g.by === "states" ? "State" : "Activity") : n.kind === "start" ? "Start" : "End"}</div>
      <h2>{n.label} <span className="muted">({n.itemKind})</span></h2>
      <Fields caption="Counts" fields={rows([["times", n.count], ["items", n.items], ["now in it", n.now]])} />
      <h3>Came from</h3>{lines(into, (e) => e.source)}
      <h3>Went on to</h3>{lines(out, (e) => e.target)}
      <p><AppLink to={`/items/${encodeURIComponent(n.itemKind)}`}>The {n.itemKind} items</AppLink></p>
    </>
  );
}
