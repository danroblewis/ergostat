import { useState, type ReactNode } from "react";
import { ago, bytesText, costText, cpuText, dur, op, tokensText } from "../../lib/format";
import { goalWord } from "../../lib/goals";
import { AgentLink } from "../links";
import { Code, Markdown } from "../Markdown";
import { diagramHref, itemHref } from "../../lib/hrefs";
import { Pager } from "../controls";
import { usePanelApi } from "../panels/usePanelApi";
import { AppLink, Async, Dl, Muted, Rich, StatusWord } from "../ui";
import { agentTally, rolesText } from "./agentParts";
import "./agents.css";

/* An agent's own page's sections (agent.js pageAgent), each also a kind of panel: what it is, by its rung; its
   definition as written; its place in the model; what it did; the end of its log. Each takes an agent as
   /api/agents/NAME answers it (`a`), its block as written (`a.spec`) and, where it shows them, its files
   (/api/agents/NAME/files). */

/** The heading of "what it is", by its rung: a person is asked, an AI agent prompted, a program run, a rule a law. */
export const RUNG_SECTION = ["What they are asked", "Its prompt", "Its specification", "How it decides", "Its program", "Its law", "Its law"];
export const rungOf = (a: any): number | null | undefined => a?.rung ?? a?.agent?.rung;

const FILE_LANG: Record<string, string> = { python: "python", shell: "bash", yaml: "yaml", json: "json", javascript: "javascript", toml: "ini", markdown: "markdown", text: "plaintext" };
/* each reference to a section of ergostat's SPEC taken out of a text for a reader (agent.js noSpec) */
const SPEC_REF = /[ \t]*(?:(?:see|ergostat's)[ \t]+)?SPEC §\d+[a-z]*(?:\.\d+[a-z]*)*(?:[ \t]*(?:,|and)[ \t]*§\d+[a-z]*(?:\.\d+[a-z]*)*)*/g;
const specRefs = (t: string) => (String(t).match(SPEC_REF) || []).length;
export const noSpec = (t: unknown) => String(t ?? "").replace(SPEC_REF, "\0").replace(/[ \t]*\([ \t]*\0[ \t]*\)/g, "")
  .replace(/\([ \t]*\0[ \t]*[,:;]?[ \t]*/g, "(").replace(/[ \t]*[,:;]?[ \t]*\0[ \t]*\)/g, ")").replaceAll("\0", "");
function RefsNote({ text }: { text: string }) {
  const n = specRefs(text);
  return n ? <p className="muted refs-note">{`${n} reference${n === 1 ? "" : "s"} to ergostat's specification left out.`}</p> : null;
}
const valueText = (v: any): ReactNode => (v == null ? null : typeof v === "object" ? <code>{JSON.stringify(v)}</code> : String(v));

function FileBox({ f, open }: { f: any; open?: boolean }) {
  return (
    <details className="agent-file" open={open}>
      <summary>{f.name}</summary>
      {f.text != null ? <><Code code={noSpec(f.text)} lang={FILE_LANG[f.format]} /><RefsNote text={f.text} /></> : <p className="muted">{f.why || "not read"}</p>}
    </details>
  );
}

function PromptPart({ sp, files }: { sp: any; files: any[] }) {
  const f = files.find((x) => x.role === "prompt"), P = sp?.params || {};
  if (f) return <><p className="muted file-name">{f.name}</p>{f.text != null ? <><Markdown source={noSpec(f.text)} /><RefsNote text={f.text} /></> : <p className="muted">{f.why || "not read"}</p>}</>;
  const t = sp?.prompt_text ?? (typeof P.prompt === "string" ? P.prompt : null);
  return t ? <Markdown source={noSpec(t)} /> : null;
}
const hasPrompt = (sp: any, files: any[]) => files.some((x) => x.role === "prompt") || sp?.prompt_text != null || typeof sp?.params?.prompt === "string";

function ProgramPart({ sp, files }: { sp: any; files: any[] }) {
  const P = sp?.params || {}, prog = files.filter((x) => x.role === "program");
  return (
    <>
      {P.run && <p>Runs <code className="command">{String(P.run)}</code></p>}
      {P.daemon && <p>{`Handed to the daemon ${P.daemon}.`}</p>}
      {sp?.own && <><p className="own"><b>{`ergostat's own: ${sp.own.module}`}</b></p>{sp.own.doc && <p className="muted">{noSpec(sp.own.doc)}</p>}</>}
      {prog.map((f, i) => <FileBox key={f.name} f={f} open={i === 0} />)}
    </>
  );
}

function LawPart({ sp }: { sp: any }) {
  const l = sp?.law || {}, P = sp?.params || {};
  if (l.error) return <p className="muted">{`Its law could not be worked out: ${l.error}`}</p>;
  const rows = (l.rows || []).filter(([, v]: [string, any]) => v != null && v !== "");
  return (
    <>
      {l.says && <p className="what law-says"><Rich text={op(l.says)} /></p>}
      <Dl rows={rows.map(([k, v]: [string, any]) => [k, typeof v === "string" ? <Rich text={op(v)} /> : v])} />
      {["table", "points", "schedule"].filter((k) => P[k] && typeof P[k] === "object").map((k) => (
        <div key={k}><h3>{k}</h3><Code code={JSON.stringify(P[k], null, 2)} lang="json" /></div>
      ))}
      {sp?.implied_by && <p className="implied-by">implied by <AgentLink name={sp.implied_by} />'s goal</p>}
    </>
  );
}

function DecidesPart({ sp }: { sp: any }) {
  const hint = sp?.decisions?.hint, m = sp?.means, all = m?.spans || [], now = all.at(-1), c = now?.counts || {};
  if (m?.work === "items") {
    return (
      <>
        <h3>What it may decide, and what it did in the window</h3>
        <ul className="answers">
          {(c.to || []).map(([s, k]: [string, number]) => <li key={s} className={k ? "answer" : "answer never"}>{s}{k ? <Muted>{` (${k})`}</Muted> : <Muted> never given</Muted>}</li>)}
          {(c.other || []).map(([w, k]: [string, number]) => <li key={`o${w}`} className="answer other"><b>other: </b>{w}<Muted>{` (${k})`}</Muted></li>)}
        </ul>
      </>
    );
  }
  return (
    <>
      <h3>What it said in the window</h3>
      {(c.said || []).length ? <ol className="decisions">{c.said.map(([w, k]: [string, number]) => <li key={w}>{w.replaceAll("#", "N")}<Muted>{` (${k})`}</Muted></li>)}</ol>
        : <p className="muted">no decisions in the window</p>}
      {hint && <p className="ladder-hint">{`${hint.controller}: “${hint.decision}” in ${Math.round(hint.share * 100)}% of ${hint.count} decisions in the window; a cheaper rung could fill it.`}</p>}
      {(c.carried || []).length > 0 && <><h3>Commands acted on</h3><Dl rows={c.carried.map((r: any) => [r.port, r.note || String(r.n)])} /></>}
    </>
  );
}

/** What it is, by its rung: a person's ask, an AI agent's prompt and wrapper, a narrow AI's specification, how a
 *  decision decides, a program's code, a rule's law. */
export function WhatItIs({ a, files }: { a: any; files: any[] }) {
  const sp = a.spec, r = rungOf(a), P = { ...(sp?.machine?.model ? { model: sp.machine.model } : {}), ...(sp?.params || {}) };
  if (r === 0) {
    const ask = P.ask ?? P.prompt;
    return <>{ask ? <Markdown source={noSpec(ask)} /> : <p className="muted">No ask written.</p>}
      <p className="asked-now">{a.running_since ? `Asked now: since ${ago(a.running_since)}, not answered yet.` : "Nothing is asked of them now."}</p></>;
  }
  if (r === 1) {
    const wrap = files.filter((x) => x.role === "wrapper");
    return (
      <>
        {hasPrompt(sp, files) ? <PromptPart sp={sp} files={files} /> : <p className="muted">No prompt written.</p>}
        <Dl rows={["model", "tools", "actions", "read", "workspace", "emits", "takes", "lease"].map((k) => [k, valueText((P as any)[k])])} />
        {(wrap.length > 0 || P.run) && (
          <details className="wrapper"><summary>Its wrapper</summary>
            {P.run && <p>Runs <code className="command">{String(P.run)}</code></p>}
            {wrap.map((f) => <FileBox key={f.name} f={f} open />)}
          </details>
        )}
      </>
    );
  }
  if (r === 2) {
    return (
      <>
        {hasPrompt(sp, files) ? <PromptPart sp={sp} files={files} /> : sp?.means?.spec ? null : <p className="muted">No prompt written.</p>}
        {(sp?.means?.spec || []).map(([shown, kv]: [string, [string, any][]]) => (
          <div key={shown}><h3>{shown}</h3><Dl rows={kv.map(([k, v]) => [k, v != null && typeof v === "object" ? valueText(v) : noSpec(String(v))])} /></div>
        ))}
      </>
    );
  }
  if (r === 3) return <>{hasPrompt(sp, files) ? <PromptPart sp={sp} files={files} /> : <ProgramPart sp={sp} files={files} />}<DecidesPart sp={sp} /></>;
  if (r === 4) return <><ProgramPart sp={sp} files={files} />{!P.run && !P.daemon && sp && <p className="muted">{sp.rung_why}</p>}</>;
  return <LawPart sp={sp} />;
}

/** Its block as written in the model's YAML, with where; or that ergostat put it in. */
export function Definition({ a }: { a: any }) {
  const sp = a.spec;
  if (!sp) return <p className="muted">Its block is not in the model's YAML.</p>;
  if (sp.implied) return <p className="implied">not written: ergostat put it in{sp.implied_by && <> front of <AgentLink name={sp.implied_by} /></>}.</p>;
  return (
    <>
      {sp.where && <p className="muted file-name">{`${sp.where.file}:${sp.where.line}`}</p>}
      {sp.source ? <><Code code={noSpec(sp.source)} lang="yaml" /><RefsNote text={sp.source} /></> : <p className="muted">Its text could not be read.</p>}
    </>
  );
}

/** The goals it serves, each a link to its evidence, with its word now (`loops`: /api/loops). */
export function Serves({ a, loops }: { a: any; loops: any }) {
  const sp = a.spec;
  const gs = [...new Set([a.place?.goal, ...(a.roles || []).map((r: any) => r.goal || (r.kind === "controller" ? r.name : null)),
    ...(sp?.decisions?.controllers || [])].filter((g) => g && loops?.[g]))] as string[];
  if (!gs.length) return null;
  return <>{gs.map((g, i) => <span key={g}>{i ? ", " : ""}<AppLink to={`/goals?select=${encodeURIComponent(g)}`} className="goal">{g}</AppLink> <StatusWord status={goalWord(loops[g])} /></span>)}</>;
}

const list = (xs: string[]) => xs.map((x, i) => <span key={x}>{i ? ", " : ""}<AgentLink name={x} /></span>);
function rungsText(sp: any): string | null {
  const s = sp?.means?.spans || [];
  const name = (x: any) => (x.first == null ? "the model now" : x.first === x.last ? `v${x.first}` : `v${x.first} to v${x.last}`);
  return s.length > 1 ? s.map((x: any) => `${x.rung ?? "not in the model"}: ${name(x)}`).join(", ") : null;
}

/** Its place in the model: the goals it serves, the roles it fills, its rung over versions, who commands it and whom
 *  it commands, what it works now; and a link to it on Blocks. */
export function Place({ a, name, loops }: { a: any; name: string; loops: any }) {
  const pl = a.place || {}, w = pl.working;
  return (
    <>
      <Dl rows={[
        ["serves", loops ? <Serves a={a} loops={loops} /> : null],
        ["fills", rolesText(a.roles) || "nothing"],
        ["its rung over versions", rungsText(a.spec)],
        ["commanded by", (pl.commanded_by || []).length ? list(pl.commanded_by) : null],
        ["commands", (pl.commands || []).length ? list(pl.commands) : null],
        ["working now", w ? (w.n == null ? "not known" : `working ${w.n} ${w.projection}${w.n === 1 ? "" : "s"}`) : null],
      ]} />
      <p><AppLink to={diagramHref({ view: "blocks", around: `block/${name}` })}>Show on Blocks</AppLink></p>
    </>
  );
}

/** What it did in the window: its runs' tally, what they cost, and its last ten runs, newest first. */
/** A run's object (the built-in projection ergostat.run): its id, from its block and its run's id. */
export const RUN = "ergostat.run";
export const runId = (block: string, run: string) => `${RUN}/${block}/${run}`;
export const runHref = (block: string, run: string) => itemHref(runId(block, run));

/** Its runs, each an object of ergostat.run, newest first, a page at a time: when, how it ended, how long, what it moved,
 *  cost, what it said; each links to its run's page (its fields, its log while kept, its session). */
function RunList({ a, name, every, refreshKey }: { a: any; name: string; every?: number | null; refreshKey?: unknown }) {
  const [at, setAt] = useState({ offset: 0, n: 10 });
  const got = usePanelApi<any>("items", { projection: RUN, where: `block:${name}`, n: at.n, offset: at.offset, eta: 0 }, every, refreshKey);
  const outcome = (i: any, run: string, f = i.fields || {}) => i.state === "running" ? <span className="s-open">running</span>
    : (a.ended || {})[run]?.how === "nack" ? <span className="s-open">refused</span>
    : i.state === "failed" ? <><span className="s-off">{f.outcome || "failed"}</span>{f.error && <Muted>{`: ${f.error}`}</Muted>}</>
      : <><span className="status">{f.outcome === "stopped" ? "stopped" : "done"}</span>{f.note && <Muted>{`: ${f.note}`}</Muted>}</>;
  return (
    <Async state={got}>
      {(d) => {
        const its: any[] = d.items || [];
        if (!its.length) return <p className="muted">No run of it is kept in the record.</p>;
        const pager = (where: "top" | "foot") => d.total > at.n || at.offset ? (
          <Pager at={where} total={d.total} offset={d.offset ?? at.offset} shown={its.length} size={at.n} sizes={[10, 25, 100]} what="runs"
            onPage={(pg) => setAt({ ...at, offset: (pg - 1) * at.n })} onSize={(n) => setAt({ offset: 0, n })} />
        ) : null;
        return (
          <>
            {pager("top")}
            <div className="table-wrap runs-table">
              <table>
                <caption className="sr-only">{`Runs of ${name}, newest first`}</caption>
                <thead><tr><th>when</th><th>item</th><th>outcome</th><th className="num">took</th><th>moved</th><th>outward actions asked</th><th className="num">cost</th><th className="num">CPU</th><th className="num">memory</th><th>said</th></tr></thead>
                <tbody>
                  {its.map((i: any) => {
                    const f = i.fields || {}, run = String(i.id).split("/").pop() || "", asked = (a.asked || {})[run] || [];
                    const said = String(f.said || "").split("\n").filter(Boolean).pop() || "";
                    return (
                      <tr key={i.id}>
                        <td className="nowrap"><AppLink to={itemHref(i.id)} title={`run ${run}`}>{ago(f.started ?? i.first)}</AppLink></td>
                        <td className="cell">{f.item ? (String(f.item).includes("/") ? <AppLink to={itemHref(f.item)}>{f.item}</AppLink> : f.item) : <Muted>none</Muted>}</td>
                        <td className="cell">{outcome(i, run)}</td>
                        <td className="num nowrap">{f.seconds != null ? dur(f.seconds) : "–"}</td>
                        <td className="cell">{f.moved || <Muted>–</Muted>}</td>
                        <td className="cell">{asked.length ? asked.map((x: any, j: number) => <span key={x.id}>{j ? ", " : ""}<AppLink to={itemHref(x.id)} title={x.state}>{x.action || x.id}</AppLink></span>) : <Muted>none</Muted>}</td>
                        <td className="num nowrap" title={f.cost ? `${f.cost}${f.ai_model ? ", " + f.ai_model : ""}` : ""}>{costText({ cost_usd: f.cost_usd, cost: f.cost, runs: 1 }, a)}{f.cost && f.cost !== "reported" && <Muted> est.</Muted>}</td>
                        <td className="num">{cpuText(f.cpu)}</td>
                        <td className="num">{bytesText(f.memory)}</td>
                        <td className="cell said" title={f.said || ""}>{said ? (said.length > 120 ? said.slice(0, 117) + "..." : said) : <Muted>nothing</Muted>}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {pager("foot")}
          </>
        );
      }}
    </Async>
  );
}

export function Runs({ a, name, every, refreshKey }: { a: any; name: string; every?: number | null; refreshKey?: unknown }) {
  const t = a.use?.totals;
  return (
    <>
      <Dl rows={agentTally(a)} />
      {t && t.runs > 0 && (
        <>
          <h3>What its runs cost</h3>
          <p className="note use-totals">{`${t.runs} runs: ${costText(t, a)}${t.cost && t.cost !== "reported" ? ` (${t.cost}: from tokens, by a price table)` : ""}, ${tokensText(t.tokens)} tokens, ${cpuText(t.cpu)} CPU, at most ${bytesText(t.memory_peak)} in one run.`}</p>
        </>
      )}
      <h3>Its runs</h3>
      <RunList a={a} name={name} every={every} refreshKey={refreshKey} />
      <p className="note"><AppLink to={`/${RUN}?q=${encodeURIComponent(name)}`}>Every run, of every agent</AppLink></p>
    </>
  );
}

/** The file its log is kept in (its name only). */
export const logFile = (a: any): string => (a?.log_path ? String(a.log_path).split(/[\\/]/).pop() || "" : "");

/** The end of its log: its last fifteen lines. */
export function LogTail({ a }: { a: any }) {
  if (!a.log?.length) return <p className="muted">{`Nothing in its log${logFile(a) ? `, ${logFile(a)},` : ""} yet.`}</p>;
  return <pre className="log-tail">{a.log.slice(-15).join("\n")}</pre>;
}
