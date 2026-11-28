import { useState, type ReactNode } from "react";
import { apiPost } from "../lib/api";
import { itemHref } from "../lib/hrefs";
import { dur } from "../lib/format";
import { goalsOff, useStatus, waitsOnYou, type Status } from "../state/status";
import { AppLink, Button, Fold } from "./ui";

/* What asks for the owner's attention (/api/status's attention, or a graph's in its own words), and the lists a
   diagram is read with: the parts of the Diagram page's side list, and of the attention, legend, feedback-loops,
   control-loops and quiet-systems panels. */

/** The parts of the attention, in the order they are drawn: what waits for the owner, the goals off, the model's
    housekeeping, the suggestions. */
export const ATTENTION_PARTS = ["waiting", "off", "housekeeping", "suggestions"] as const;
export type AttentionPart = typeof ATTENTION_PARTS[number];

const KIND_WORD: Record<string, string> = { change: "model change", action: "action", steptest: "step test", command: "command" };

/** One thing the owner can answer here: what it is (linked to its page), why in a line, and its answers as buttons. */
function WaitingCard({ a }: { a: any }) {
  const { refresh } = useStatus();
  const [said, setSaid] = useState<string | null>(null);
  const verbs: string[] = (a.answer || []).filter((v: string) => v === "approve" || v === "deny");
  const kind = KIND_WORD[a.kind] || a.kind || "";
  const title = String(a.first || a.what).replace(/^model change: /, "");
  const give = (verb: string) => {
    const note = verb === "deny" ? window.prompt("Why? (optional)") ?? undefined : undefined;
    apiPost(`inbox/${encodeURIComponent(a.what)}/${verb}`, note ? { note } : {})
      .then(() => { setSaid(verb === "approve" ? "Approved" : "Denied"); refresh(); })
      .catch((e) => setSaid(`Not answered: ${e.message}`));
  };
  return (
    <div className="wait-card" data-row={a.what}>
      <div className="wait-title">
        {a.link ? <AppLink className="plain" to={a.link}><b>{title}</b></AppLink> : <b>{title}</b>}
      </div>
      <div className="wait-meta">{kind}{a.age ? ` · waiting ${a.age}` : ""}</div>
      {a.more && <div className="wait-why">{a.more}</div>}
      {said ? <div className="wait-said" data-answered>{said}</div> : (
        <div className="wait-actions">
          {verbs.map((v) => (
            <Button key={v} className={v === "approve" ? "primary" : undefined} data-answer={v} onClick={() => give(v)}>
              {v === "approve" ? "Approve" : "Deny"}
            </Button>
          ))}
          {(a.workbench || []).map((w: any) => (
            <AppLink key={w.projection} to={w.link} data-workbench={w.projection}>Open {w.projection} in the workbench</AppLink>
          ))}
        </div>
      )}
    </div>
  );
}

/** Whether the owner can answer it here (approve or deny). */
const answerable = (a: any): boolean => (a.answer || []).some((v: string) => v === "approve" || v === "deny");

function Row({ a, onGoal }: { a: any; onGoal: (goal: string) => void }) {
  const word = a.state || (a.kind === "request" ? "request" : waitsOnYou(a) ? "waiting" : a.level === "bad" ? "fault" : "note");
  const what = <b className={a.level === "bad" ? "lvl-bad" : "lvl-warn"}>{a.what}</b>;
  const href = a.item ? itemHref(a.item) : a.link || null;
  return (
    <div data-row={a.what}>
      <span className="att-word">{word} · </span>
      {href ? <AppLink className="plain" to={href}>{what}</AppLink>
        : a.goal ? <button type="button" className="name" onClick={() => onGoal(a.goal)}>{what}</button> : what}{" "}
      {String(a.says || "").replace(/\. ergostat inbox .*$/, "")}
      {a.diagnosis_in ? <span className="muted"> · diagnosis in {dur(a.diagnosis_in)}</span> : null}
      {a.stuck ? (
        <div className="att-stuck" data-stuck>where it stops: {a.stuck_link ? <AppLink to={a.stuck_link}>{a.stuck}</AppLink> : a.stuck}</div>
      ) : null}
    </div>
  );
}

/** The attention entries, those parts of them asked for (``show``, all when none). A row waiting links to its entry
 *  (a change's page, a drafted projection in the workbench) and is answered there or by its Approve / Deny. */
export function Attention({ attention, status, show, onGoal }: {
  attention: any[]; status?: Status; show?: readonly AttentionPart[] | null; onGoal: (goal: string) => void;
}) {
  const shown = (p: AttentionPart) => !show?.length || show.includes(p);
  const problems = attention.filter((a) => a.level !== "hint"), hints = attention.filter((a) => a.level === "hint");
  const waiting = problems.filter(waitsOnYou).sort((x, y) => Number(answerable(y)) - Number(answerable(x)));   // answerable here first
  const off = problems.filter((a) => a.state === "off").sort((a, b) => Number(!!a.modelling) - Number(!!b.modelling));
  const rest = problems.filter((a) => !waitsOnYou(a) && !off.includes(a));
  const { off: nOff, upkeep } = goalsOff(status);
  const list = (xs: any[], none: string, cls: string) => (
    <div className={`att ${cls}`}>
      {!xs.length && <div className="none">{none}</div>}
      {xs.map((a, i) => <Row key={a.what + i} a={a} onGoal={onGoal} />)}
    </div>
  );
  return (
    <>
      {shown("waiting") && (
        <>
          {status && !status.running && <div className="att"><div><b className="lvl-warn">Not running. </b>These are the last readings.</div></div>}
          {waiting.length > 0 ? (
            <>
              <h3 className="att-head" id="waiting" tabIndex={-1}>Waiting for you <span className="muted">{waiting.length}</span></h3>
              {waiting.filter(answerable).map((a, i) => <WaitingCard key={a.what + i} a={a} />)}
              {list(waiting.filter((a) => !answerable(a)), "", "needs")}
            </>
          ) : <p id="may-do" className="may-do">Nothing waits for you. Looking never changes the system.</p>}
        </>
      )}
      {shown("off") && (
        <>
          <h3 className="att-head">Goals off <span className="muted">{nOff}{upkeep ? ` · model upkeep ${upkeep}` : ""}</span></h3>
          {list(off, "No goal is off.", "goals-off")}
        </>
      )}
      {shown("housekeeping") && (
        <Fold className="housekeeping" open={rest.some((a) => a.level === "bad")} summary={<h3 className="att-head">Model housekeeping <span className="muted">{rest.length}</span></h3>}>
          {list(rest, "Nothing to tidy.", "house")}
        </Fold>
      )}
      {shown("suggestions") && hints.length > 0 && (
        <Fold className="suggest" summary={`Suggestions (${hints.length})`}>
          {hints.map((a, i) => <div key={i} className="hint"><b>{a.what}</b> {a.says}</div>)}
        </Fold>
      )}
    </>
  );
}

/* How to read each view's drawing: its marks, each with its meaning. */

export const VIEWS = ["dynamics", "blocks", "process"] as const;
export type View = typeof VIEWS[number];

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

/** What each view's drawing is called. */
export const LEGEND_TYPE: Record<string, string> = { dynamics: "stock and flow diagram", blocks: "block diagram", process: "process map" };

const GLYPH: Record<string, ReactNode> = {
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

/** How to read a view's drawing: each of its marks and what it means. */
export function Legend({ view }: { view: string }) {
  return (
    <div className="legend" data-view={view}>
      {(LEGEND[view] || []).map(([k, v]) => <Glyph key={k} k={k} v={v} />)}
    </div>
  );
}

/** The feedback loops a stock and flow diagram (its graph, /api/graph?view=dynamics) draws, each with its polarity. */
export function FeedbackLoops({ g }: { g: any }) {
  const causal: any[] = g?.causalLoops || [];
  return (
    <>
      {!causal.length && <div className="muted">No feedback loops in view.</div>}
      {causal.map((c) => (
        <div key={c.name} className="looprow"><b>{c.polarity || "?"}</b> {c.name}{c.goal ? <span className="muted"> · closes {c.goal}</span> : null}</div>
      ))}
    </>
  );
}

/** How many feedback loops a stock and flow diagram draws, in words. */
export const feedbackCount = (g: any): string =>
  g?.loopCount ? `${g.loopCount.named} named, ${g.loopCount.minor} minor` : String((g?.causalLoops || []).length);

/** The control loops a block diagram (its graph, /api/graph?view=blocks) draws: each goal, its status, what it holds. */
export function ControlLoops({ g, onGoal }: { g: any; onGoal: (goal: string) => void }) {
  const loops = Object.entries(g?.loops || {});
  return (
    <>
      {!loops.length && <div className="muted">No control loops in view.</div>}
      {loops.map(([name, lp]: [string, any]) => (
        <button key={name} type="button" className="looprow" data-loop={name} onClick={() => onGoal(name)}>
          <b>{name}</b> <span className={`status s-${lp.status}`}>{lp.status}</span>
          <div className="sub">{lp.stock} {lp.setpoint}{lp.value != null ? `, now ${lp.value}` : ""}</div>
        </button>
      ))}
    </>
  );
}

/** Each closed system whose every goal holds, in its own sentence (/api/systems's quiet). */
export function QuietSystems({ systems, none }: { systems: any[]; none?: ReactNode }) {
  const quiet = (systems || []).filter((s) => s.quiet);
  return (
    <div className="quiet-systems">
      {!quiet.length && none}
      {quiet.map((s) => (
        <p key={s.name} className="quiet-line" data-system={s.name}><b>{s.name}</b>: {s.quiet}</p>
      ))}
    </div>
  );
}
