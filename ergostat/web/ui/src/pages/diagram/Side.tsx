import { AppLink, Fold } from "../../components";
import { ago, dur } from "../../lib/format";
import { goalsOff, useStatus, waitsOnYou } from "../../state/status";

/* The list beside the diagram (diagram.js's renderSide): what waits for the owner, the goals off, the model's
   housekeeping, suggestions, then the view's own list (feedback loops, control loops, kinds of item). The inbox's
   answer buttons are not ported: a row waiting links to where it is answered. */

const LEGEND: Record<string, [string, string][]> = {
  dynamics: [
    ["stock (level)", "what accumulates; it changes only by its flows"],
    ["flow (rate)", "a pipe with its valve, into or out of a stock; the head shows which way"],
    ["connector, + / − / ?", "the cause rises, the effect rises above (+) or falls below (−) what it would have been; ? not known"],
    ["module", "a system closed: its connection points are what crosses its edge (Open draws its parts in place; Into draws it alone)"],
  ],
  blocks: [
    ["a block", "its function inside: C a controller, P a process; click it for its definition"],
    ["a system as one block", "C_name when it acts on another system's process, P_name when acted on"],
    ["r e u y d", "reference, error (r − y_m), control signal, output, disturbance; subscripts name the loop or the part"],
  ],
  process: [
    ["a box", "a state items entered, or an event about them; darker the more often"],
    ["a line", "one followed the other: how many times, or the median time between (Times)"],
  ],
};

const LEGEND_TYPE: Record<string, string> = { dynamics: "stock and flow diagram", blocks: "block diagram", process: "process map" };
const GLYPH: Record<string, React.ReactNode> = {
  "stock (level)": <rect x={3} y={4} width={20} height={12} fill="none" stroke="var(--ink)" strokeWidth={1.4} />,
  "flow (rate)": <path d="M1,8 H24 M1,12 H24 M8,5 L13,10 L8,15 Z M18,5 L13,10 L18,15 Z" fill="none" stroke="var(--ink)" strokeWidth={1.2} />,
  "connector, + / − / ?": <path d="M3,15 Q12,2 22,8" fill="none" stroke="var(--ink)" strokeWidth={1.2} />,
  module: <rect x={2} y={3} width={22} height={14} rx={4} fill="none" stroke="var(--ink)" strokeWidth={1.2} />,
  "a block": <rect x={3} y={4} width={20} height={12} fill="none" stroke="var(--ink)" strokeWidth={1.2} />,
  "a system as one block": <rect x={2} y={3} width={22} height={14} fill="none" stroke="var(--ink)" strokeWidth={1.6} />,
  "a box": <rect x={2} y={4} width={22} height={12} rx={3} fill="none" stroke="var(--ink)" strokeWidth={1.2} />,
  "a line": <path d="M2,10 H20 M16,6 L22,10 L16,14" fill="none" stroke="var(--ink)" strokeWidth={2} />,
};
function Glyph({ k, v }: { k: string; v: string }) {
  return (
    <>
      {GLYPH[k] ? <svg width={26} height={20} aria-hidden="true">{GLYPH[k]}</svg> : <span className="sym">{k}</span>}
      <span>{GLYPH[k] ? `${k}: ` : ""}{v}</span>
    </>
  );
}

function Row({ a, onGoal }: { a: any; onGoal: (goal: string) => void }) {
  const word = a.state || (a.kind === "request" ? "request" : waitsOnYou(a) ? "waiting" : a.level === "bad" ? "fault" : "note");
  const what = <b className={a.level === "bad" ? "lvl-bad" : "lvl-warn"}>{a.what}</b>;
  const href = a.item ? `/item/${encodeURIComponent(a.item)}` : null;
  return (
    <div data-row={a.what}>
      <span className="att-word">{word} · </span>
      {href ? <AppLink className="plain" to={href}>{what}</AppLink>
        : a.goal ? <button type="button" className="name" onClick={() => onGoal(a.goal)}>{what}</button> : what}{" "}
      {String(a.says || "").replace(/\. ergostat inbox .*$/, "")}
      {a.diagnosis_in ? <span className="muted"> · diagnosis in {dur(a.diagnosis_in)}</span> : null}
    </div>
  );
}

export function Side({ g, view, onGoal, onPick }: { g: any; view: string; onGoal: (goal: string) => void; onPick: (n: any) => void }) {
  const { status: st } = useStatus();
  const all: any[] = g?.attention || st?.attention || [];
  const problems = all.filter((a) => a.level !== "hint"), hints = all.filter((a) => a.level === "hint");
  const waiting = problems.filter(waitsOnYou);
  const off = problems.filter((a) => a.state === "off").sort((a, b) => Number(!!a.modelling) - Number(!!b.modelling));
  const rest = problems.filter((a) => !waitsOnYou(a) && !off.includes(a));
  const { off: nOff, upkeep } = goalsOff(st);
  const list = (xs: any[], none: string, cls: string) => (
    <div className={`att ${cls}`}>
      {!xs.length && <div className="none">{none}</div>}
      {xs.map((a, i) => <Row key={a.what + i} a={a} onGoal={onGoal} />)}
    </div>
  );
  const loops = Object.entries(g?.loops || {});
  const causal: any[] = g?.causalLoops || [];
  return (
    <>
      {st && !st.running && <div className="att"><div><b className="lvl-warn">Not running. </b>These are the last readings.</div></div>}
      {waiting.length > 0 ? (
        <>
          <h3 className="att-head" id="waiting" tabIndex={-1}>Waiting for you <span className="muted">{waiting.length}</span></h3>
          {list(waiting, "", "needs")}
        </>
      ) : <p id="may-do" className="may-do">Nothing waits for you. Looking never changes the system.</p>}
      <Fold className="legend-box" open summary={<>How to read it<span className="muted"> · the {LEGEND_TYPE[view]}</span></>}>
        <div className="legend">
          {(LEGEND[view] || []).map(([k, v]) => <Glyph key={k} k={k} v={v} />)}
        </div>
      </Fold>
      <h3 className="att-head">Goals off <span className="muted">{nOff}{upkeep ? ` · model upkeep ${upkeep}` : ""}</span></h3>
      {list(off, "No goal is off.", "goals-off")}
      <Fold className="housekeeping" open={rest.some((a) => a.level === "bad")} summary={<h3 className="att-head">Model housekeeping <span className="muted">{rest.length}</span></h3>}>
        {list(rest, "Nothing to tidy.", "house")}
      </Fold>
      {hints.length > 0 && (
        <Fold className="suggest" summary={`Suggestions (${hints.length})`}>
          {hints.map((a, i) => <div key={i} className="hint"><b>{a.what}</b> {a.says}</div>)}
        </Fold>
      )}
      {view === "dynamics" && (
        <Fold className="loops" summary={<>Feedback loops <span className="muted">{g?.loopCount ? `${g.loopCount.named} named, ${g.loopCount.minor} minor` : causal.length}</span></>}>
          {!causal.length && <div className="muted">No feedback loops in view.</div>}
          {causal.map((c) => (
            <div key={c.name} className="looprow"><b>{c.polarity || "?"}</b> {c.name}{c.goal ? <span className="muted"> · closes {c.goal}</span> : null}</div>
          ))}
        </Fold>
      )}
      {view === "blocks" && (
        <Fold className="loops" summary={<>Control loops <span className="muted">{loops.length}</span></>}>
          {!loops.length && <div className="muted">No control loops in view.</div>}
          {loops.map(([name, lp]: [string, any]) => (
            <button key={name} type="button" className="looprow" data-loop={name} onClick={() => onGoal(name)}>
              <b>{name}</b> <span className={`status s-${lp.status}`}>{lp.status}</span>
              <div className="sub">{lp.stock} {lp.setpoint}{lp.value != null ? `, now ${lp.value}` : ""}</div>
            </button>
          ))}
        </Fold>
      )}
      {view === "process" && (
        <Fold className="loops" open summary={<>Kinds of item <span className="muted">{(g?.kinds || []).length}</span></>}>
          {(g?.kinds || []).map((k: any) => (
            <div key={k.name}><AppLink to={`/items/${encodeURIComponent(k.name)}`}>{k.name}</AppLink> <span className="muted">{k.items} item{k.items === 1 ? "" : "s"} · {k.by}</span></div>
          ))}
          {g?.since && <p className="muted small">since {ago(g.since)}{g.capped ? ", capped" : ""}</p>}
          {(g?.nodes || []).filter((n: any) => n.now).map((n: any) => (
            <div key={n.id}><button type="button" className="name" onClick={() => onPick(n)}>{n.label}</button> <span className="muted">now {n.now}</span></div>
          ))}
        </Fold>
      )}
    </>
  );
}
