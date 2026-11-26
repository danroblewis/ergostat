import { useState } from "react";
import { AgentLink } from "./links";
import { Async, Button, Dl, Muted, Rich, StatusWord } from "./ui";
import { useApi, type ApiState } from "../hooks/useApi";
import { apiPost, isPublic } from "../lib/api";
import { ago, dur, FLAP_AT, fmt, holdText, op, rateText, shareText } from "../lib/format";
import { useStatus } from "../state/status";
import { useTime } from "../state/time";
import { exceptional, goalBound, goalOffFor, goalWord, performanceWord } from "../lib/goals";

/* A goal's parts as the goal-runbook, goal-parts and goal-control panels draw them, and as its detail (GoalDetail)
   is composed of: its runbook (four lines), the remedy and its numbers (a /api/loops/NAME answer); its parts along the
   loop; and its control loop (control.js, /api/loop-control): the process identified, its controller, and the
   proposals the owner accepts or dismisses. */

function unlisted(lp: any): string {
  const n = lp.openings_total, m = lp.row?.measure ?? lp.stock;
  if (Array.isArray(lp.valves) && !lp.valves.length) {
    return lp.through?.length ? `It is acted on through ${lp.through.map((x: string) => x.replace(/^[a-z]+\./, "")).join(" → ")}; what each did is not counted here`
      : Array.isArray(lp.through) ? `No block acts for it: nothing that reads it or ${m} moves ${m}, directly or through what it commands`
        : "What acts on it is not known";
  }
  return `No agent that acts for it is recorded; ${n == null ? "whether its valves opened is not known"
    : n ? `its valves opened ${n} time${n === 1 ? "" : "s"} in this window` : "its valves did not open in this window"}`;
}

function Runbook({ lp, at }: { lp: any; at: number | null }) {
  const word = goalWord(lp), far = lp.off_by_words ? `, ${lp.off_by_words}` : "", off = goalOffFor(lp, at);
  const usual = lp.back_in != null ? `it usually holds again ${dur(lp.back_in)} after going off (${lp.times_off} times)`
    : "it has not gone off and come back in this window, so there is no usual time yet";
  const acts = lp.actors || [];
  return (
    <div className="runbook">
      <p className="runbook-line"><StatusWord status={word} />{`: ${lp.row?.measure ?? lp.stock} should be ${goalBound(lp)}${lp.per ? `, each ${lp.per}` : ""}; it is ${fmt(lp.row ? lp.row.value : lp.value)} now${far}.`}</p>
      <p className="runbook-line">{off ? `${off.charAt(0).toUpperCase()}${off.slice(1)}; ${usual}.` : `${exceptional(word) ? `Not known to be off (${word})` : "Not off now"}; when off, ${usual}.`}</p>
      <p className="runbook-line">
        {acts.length ? acts.map((a: any, i: number) => (
          <span key={a.name}>{i ? "; " : ""}<span className="actor-line"><b><AgentLink name={a.name} /></b>
            {`: commanded ${a.commanded} time${a.commanded === 1 ? "" : "s"}, ran ${a.ran}, ` + (a.moved == null ? "what it moved is not measured" : a.moved ? `moved ${fmt(a.moved)}` : "moved nothing") + (a.log ? ` (its log: ${a.log})` : "")}
          </span></span>
        )) : lp.open_loop ? "It acts on its schedule and reads nothing" : unlisted(lp)}.
      </p>
    </div>
  );
}

export function GoalParts({ name, lp }: { name: string; lp: any }) {
  return (
    <table className="parts">
      <caption className="sr-only">{`The parts along loop ${name}`}</caption>
      <thead><tr><th>part</th><th>name</th><th>filled by</th><th>last</th></tr></thead>
      <tbody>
        {(lp.parts || []).map((pt: any, i: number) => (
          <tr key={i}>
            <td>{pt.kind}</td>
            <td><b>{pt.name}</b>{pt.kind === "valve" && <Muted>{` ${pt.mode}${pt.max ? `, ≤ ${fmt(pt.max)} a run` : ""}`}</Muted>}</td>
            <td>{pt.agent ? <span><AgentLink name={pt.agent.name} /><Muted>{` ${pt.agent.kind}`}</Muted></span> : !pt.last ? <span className="s-open">unfilled</span> : ""}</td>
            <td>
              {pt.kind === "sensor" ? (pt.last ? `read ${ago(pt.last.time)}: ${fmt(pt.last.value)}` : <Muted>no reading yet</Muted>)
                : pt.kind === "controller" ? (pt.last ? `decided ${ago(pt.last.time)}: ${pt.last.data.decision}` : <Muted>{pt.open_loop ? "acts on its schedule, reads nothing" : "no decision yet"}</Muted>)
                  : pt.last ? `opened ${ago(pt.last.time)}: ${fmt(pt.last.amount)}${pt.last.count > 1 ? ` in ${pt.last.count} openings` : ""}` : <Muted>never opened</Muted>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const secs = (x: number | null | undefined) => (x == null ? "–" : x < 600 ? `${fmt(x)} s` : dur(x));
const pm = (v: number, se?: number) => (se != null ? `${fmt(v)} ± ${fmt(se)}` : fmt(v));
const pc = (x: number | null | undefined) => (x == null ? "–" : `${Math.round(x)}%`);
const procText = (p: any, se: any = {}) =>
  `K ${pm(p.K, se.K)}, ${p.form === "integrating" ? "an integrator" : `τ ${pm(p.tau, se.tau)} s`}, θ ${pm(p.theta, se.theta)} s`;

/** An owner's answer to a proposal of the loop's: accept (or approve a step test) or dismiss. */
function Proposal({ x, onDone }: { x: any; onDone: () => void }) {
  const test = x.kind === "step-test";
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ text: string; bad?: boolean } | null>(null);
  const answer = async (what: "accept" | "dismiss") => {
    setBusy(true);
    setSaid({ text: what === "accept" ? (test ? "Approving…" : "Applying the edit…") : "" });
    try {
      const got = await apiPost(`control/${encodeURIComponent(x.id)}/${what}`);
      setSaid({ text: what === "dismiss" ? "Dismissed: it is not offered again until the loop changes in the model."
        : test ? "Approved: ergostat runs it now, and the record will show it."
          : `Accepted: ${(got.edit?.files || []).map((f: any) => String(f.file).split(/[\\/]/).pop()).join(", ")} changed.` });
      onDone();
    } catch (e) {
      setSaid({ text: String((e as Error).message || e), bad: true });
      setBusy(false);
    }
  };
  const kind = ({ process: "Proposed process", tuning: "Proposed tuning", "step-test": "Proposed step test" } as Record<string, string>)[x.kind] || "Proposed";
  return (
    <div className="proposal">
      <div className="proposal-title"><span className="muted small">{kind}</span><div>{x.title}</div></div>
      {test ? <details><summary className="small">how it is sized</summary><p className="muted small">{x.reason}</p></details>
        : <p className="muted small">{x.reason}</p>}
      {x.edit?.diff && (
        <pre className="diff">{String(x.edit.diff).split("\n").map((l: string, i: number) => (
          <div key={i} className={l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : "muted"}>{l}</div>))}</pre>
      )}
      {isPublic() ? <p className="muted small">Answered where the model is, not in this page.</p> : (
        <div className="actions">
          <Button disabled={busy} onClick={() => answer("accept")}>{test ? "Approve" : "Accept"}</Button>
          <Button variant="ghost" disabled={busy} onClick={() => answer("dismiss")}>Dismiss</Button>
        </div>
      )}
      {said?.text && <p className={said.bad ? "s-open small" : "small"}>{said.text}</p>}
    </div>
  );
}

/** The goal's control loop (api loop-control): its law, its process identified, how it is doing, and the proposals. */
export function GoalControl({ ctl, off }: { ctl: ApiState<any>; off?: number }) {
  const { refresh: refreshStatus } = useStatus();
  return (
    <Async state={ctl} what="Its control loop">
      {(d) => {
        if (d.why) return <p className="muted small">{`The control loop of goal ${d.goal}: ${d.why}.`}</p>;
        const c = d.controller || {}, r = d.identified || {}, p = r.found ? r : d.process, pf = d.performance || {}, ex = pf.excursions || {};
        const law = `${c.block ? c.block + ": " : ""}${c.says || "not known"}${c.law?.form === "I" ? `, gain ${fmt(c.law.g)} a step`
          : c.law?.form === "PI" ? `, K_c ${fmt(c.law.Kc)}, τ_I ${secs(c.law.Ti)}` : ""}`;
        const u = (d.u || "").split(".").slice(1).join("."), y = (d.y || "").split(".").slice(1).join(".");
        const done = () => { ctl.refresh(); refreshStatus(); };
        return (
          <div className="control-box">
            <h3 data-goal={d.goal}>{`The control loop of goal ${d.goal}, from u to y`}</h3>
            <p className="muted small">{`u: ${u} (${d.how === "valve" ? "what its valve moves, a rate" : "the setting its controller steps"}); y: ${y}.`}</p>
            {d.known && <p className="small">{d.known}.</p>}
            <table className="loop-table">
              <caption>{`The loop ${d.goal}`}</caption>
              <tbody>
                <tr><th>law</th><td><Rich text={law} /></td></tr>
                <tr><th>process</th><td>{p ? procText(p, r.found ? r.se || {} : {}) : "not identified: needs a step of u"}{d.declared ? <Muted>{d.declared.identified ? ` (in the model, identified ${d.declared.identified})` : " (in the model, declared)"}</Muted> : null}</td></tr>
                <tr><th>held-out fit</th><td>{`estimation ${pc(r.fit_est)}, validation ${pc(r.fit_val)} `}<Muted>(NRMSE fit, 100% is perfect, below 0 is worse than the mean)</Muted></td></tr>
                <tr><th>time off</th><td>{off != null ? pc(off * 100) : "–"}</td></tr>
                <tr><th>settling</th><td>{ex.count ? `${secs(ex.settling)}, typically` : "–"}</td></tr>
                <tr><th>saturation</th><td>{pf.saturation != null ? `${pc(pf.saturation * 100)} of the ${d.how === "valve" ? "openings" : "time"}` : "–"}</td></tr>
                <tr><th>how it is doing</th><td>{performanceWord(d) || "–"}</td></tr>
              </tbody>
            </table>
            {r.found && !r.proposable && <p className="muted small">{`Not proposed: ${(r.why || []).join("; ")}.`}</p>}
            {(d.proposals || []).map((x: any) => <Proposal key={x.id} x={x} onDone={done} />)}
          </div>
        );
      }}
    </Async>
  );
}


/** The goal's control loop, asking for it itself (every 8 s, as the record is now). */
export function GoalControlBox({ goal, off }: { goal: string; off?: number }) {
  const ctl = useApi<any>("loop-control", { goal }, { every: 8000, window: false });
  return <GoalControl ctl={ctl} off={off} />;
}

/** A goal's runbook (what it holds, whether it is off and for how long usually, who acts for it), the remedy, and its
 *  numbers, from its /api/loops/NAME answer. */
export function GoalRunbook({ name, lp }: { name: string; lp: any }) {
  const { status } = useStatus();
  const { at } = useTime();
  const recorded = Math.min(lp.until - lp.since, status?.first ? lp.until - status.first : Infinity);
  const windowWords = recorded < (lp.until - lp.since) * 0.95 ? `of the ${dur(recorded)} recorded` : "of the window";
  const word = goalWord(lp);
  const remedies = (lp.hints || []).filter((x: any) => x.about === "loop").map((x: any) => op(x.says));
  return (
    <>
      <Runbook lp={lp} at={at} />
      {remedies.map((t: string, i: number) => <p key={i} className="remedy"><b>Remedy: </b>{t}</p>)}
      {lp.description && <p className="muted">{lp.description}</p>}
      {lp.open_loop && <p>It acts on its schedule and reads nothing; its sensor only watches it against the setpoint.</p>}
      <Dl rows={[
        ["status", <StatusWord status={word} />],
        ["holds", `${lp.stock}, ${holdText(lp.setpoint, lp.band)}${lp.per ? `, each ${lp.per}` : ""}`],
        ["now", lp.per ? `${fmt(lp.value)}, the worst ${lp.per}'s` : fmt(lp.value)],
        ["stale", lp.stale != null ? `read ${dur(lp.stale)} ago, too long for its sensor; on-stale: ${lp.on_stale}` : null],
        ["how far", lp.off_by_words || null],
        ["time off", `${shareText(lp.off_share)} ${windowWords}` + (lp.times_off >= FLAP_AT ? `; flapping: ${lp.times_off} crossings, off and back` : "")],
        ["typically", lp.answers_in != null || lp.back_in != null ? [
          lp.answers_in != null ? `its valve opens ${dur(lp.answers_in)} after it goes off` : null,
          lp.back_in != null ? `it holds again ${dur(lp.back_in)} after (slowest ${dur(lp.back_in_slowest)}, ${lp.times_off} times)` : null,
        ].filter(Boolean).join("; ") : null],
        ["moves", Object.entries(lp.moves || {}).map(([f, r]) => `${f} ${rateText(r as number, "", status?.rate_units?.[f])}`).join(", ") || null],
        ["cycled", lp.observed ? "yes, in this window" : "not in this window"],
      ]} />
      {lp.control_loop && (
        <p className="goal-loops">Feedback loops: {(lp.feedback_loops || []).length
          ? lp.feedback_loops.map((c: any) => `${c.label} ${c.name}`).join(", ") : <Muted>none</Muted>} (Dynamics) · Control loop: {lp.control_loop.controllers.join(", ") || name} (Blocks)</p>
      )}
    </>
  );
}
