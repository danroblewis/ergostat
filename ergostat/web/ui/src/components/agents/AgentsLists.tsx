import { Fragment } from "react";
import { ago, bytesText, costText, cpuText, op, tokensText, usd, windowNote } from "../../lib/format";
import { agentHref, itemHref } from "../../lib/hrefs";
import { RUNG_HINT, RUNG_NAMES } from "../../lib/rung";
import { useStatus } from "../../state/status";
import { WINDOW_WORDS, useTime } from "../../state/time";
import { Table } from "../Table";
import { AppLink, Muted, Note } from "../ui";
import { exception, lastText, rolesText } from "./agentParts";

/* The Agents page's parts (pages.js pageAgents), each also a kind of panel: the ladder, one list by rung from the most
   general agent to none with what each costs in the window, and the daemons. Each takes /api/agents (or
   /api/daemons) as its endpoint answers. */

const COLS = [...RUNG_NAMES, "retired"] as string[];
type Num = [key: string, head: string, title: string, cell: (u: any) => number | null | undefined, text: (n: any) => string, total: () => number];

/** How many agents fill each rung, most general first, and how many stand out (failed, never ran, behind). */
export function LadderLine({ agents }: { agents: Record<string, any> }) {
  const of = (i: number) => Object.values(agents).filter((a) => a.rung === i).length;
  const tally: Record<string, number> = {};
  for (const a of Object.values(agents)) {
    const x = exception(a);
    if (x) { const k = x[0].startsWith("behind") ? "behind schedule" : x[0]; tally[k] = (tally[k] || 0) + 1; }
  }
  return (
    <div className="ladder-line">
      {COLS.map((k, i) => (
        <span key={k} className="step" data-kind={k} title={RUNG_HINT[i]}>{of(i) ? <b>{of(i)}</b> : "0"}{` ${k}`}</span>
      ))}
      <Muted>most general → most specific</Muted>
      {Object.entries(tally).map(([k, n]) => <span key={k} className="exception">{`${n} ${k}`}</span>)}
    </div>
  );
}

/** What the runs cost, in words: the agents table's note. */
export function CostNote() {
  const { status } = useStatus();
  const { since } = useTime();
  const w = WINDOW_WORDS[since] ? `over the ${WINDOW_WORDS[since].toLowerCase()}` : windowNote(status);
  return (
    <Note>
      {`What the runs cost${w ? ", " + w : ""}: dollars their AI sessions cost (as Claude Code reported them; "est." where only tokens were known and a price table priced them), their tokens, the CPU time of each run's processes (user and system), and the most memory one run held. Open an agent for what it is and its history, run by run.`}
    </Note>
  );
}

/** Every agent, grouped by rung: its roles, runs, last run, schedule and what its runs cost, with the window's totals. */
export function AgentsTable({ agents, caption = "Agents, by rung", mark, label }: {
  agents: Record<string, any>; caption?: string;
  /** a row's class and title (an ancillary agent: greyer, saying where it is defined) */
  mark?: (name: string) => { className?: string; title?: string };
  label?: (name: string) => string;
}) {
  const of = (i: number) => Object.entries(agents).filter(([, a]) => a.rung === i);
  const groups = COLS.map((k, i) => [i, k, of(i)] as const).filter(([, , xs]) => xs.length);
  const use = (a: any) => a.use || {};
  const all = Object.values(agents);
  const sum = (f: (u: any) => any) => all.reduce((s, a) => s + (f(use(a)) || 0), 0);
  const nums = ([
    ["tokens", "tokens", "Tokens its AI sessions used in the window: input, output, cache reads and writes", (u) => (u.ai_runs ? u.tokens : null), tokensText, () => sum((u) => u.ai_runs && u.tokens)],
    ["cpu", "CPU", "CPU time of its runs' processes in the window, user and system", (u) => u.cpu, cpuText, () => sum((u) => u.cpu)],
    ["memory", "peak memory", "The most memory one of its runs held (its processes together)", (u) => u.memory_peak, bytesText, () => Math.max(...all.map((a) => use(a).memory_peak || 0))],
  ] as Num[]).filter(([, , , v]) => all.some((a) => v(use(a)) != null));
  const spent = sum((u) => u.cost_usd);
  const unk = all.reduce((s, a) => s + (([1, 2, 3].includes(a.rung) && use(a).unknown) || 0), 0);
  const gap = unk ? `not known: ${unk} failed or stopped` : "";
  const span = 6 + nums.length;
  if (!all.length) return <p className="muted">No agents in the model.</p>;
  return (
    <Table caption={caption}>
      <Table.Head>
        <Table.Th>agent</Table.Th><Table.Th>roles</Table.Th><Table.Th num>runs</Table.Th><Table.Th>last run</Table.Th><Table.Th>runs when</Table.Th>
        <Table.Th num title="What its AI sessions cost in the window, in USD; a stand-in or a program runs free">cost</Table.Th>
        {nums.map(([k, head, title]) => <Table.Th key={k} num title={title}>{head}</Table.Th>)}
      </Table.Head>
      {groups.map(([i, k, xs]) => (
        <Table.Body key={k} className="group">
          <tr>
            <th colSpan={span} scope="colgroup" data-kind={k}>{`${k} · `}<span className="count">{xs.length}</span><small className="muted">{`  rung ${i}, ${RUNG_HINT[i]}`}</small></th>
          </tr>
          {xs.map(([name, a]) => {
            const x = exception(a), u = use(a);
            return (
              <Fragment key={name}>
                <Table.Row to={agentHref(name)} {...mark?.(name)}>
                  <Table.Td className="nowrap">
                    <AppLink to={agentHref(name)} className="agent-link"><b>{label?.(name) ?? name}</b></AppLink>
                    {x && <span className="exception" title={x[1]}>{` ${x[0]}`}</span>}
                  </Table.Td>
                  <Table.Td>
                    {rolesText(a.roles) || <Muted>no roles</Muted>}
                    {(a.hints || []).length > 0 && (
                      <ul className="hints">
                        {a.hints.map((hint: any, j: number) => (
                          <li key={j} className={hint.about === "loop" ? "warn" : ""} title={hint.says}>
                            {hint.about === "loop" ? op(hint.says)
                              : `${hint.controller}: “${hint.decision}” ${Math.round(hint.share * 100)}% of ${hint.count}; a cheaper rung could fill it`}
                          </li>
                        ))}
                      </ul>
                    )}
                  </Table.Td>
                  <Table.Td num>{a.collects ? "–" : String(a.runs ?? "")}</Table.Td>
                  <Table.Td className="nowrap muted">{a.last?.causedby && !a.running_since && !a.collects ? <AppLink to={itemHref(`ergostat.run/${name}/${a.last.causedby}`)} title="its last run">{lastText(a)}</AppLink> : lastText(a)}</Table.Td>
                  <Table.Td className="muted">{a.collects ? "continuously (a daemon)" : a.schedule || a.every || (a.leased ? "on demand, per item (leased)" : a.runs_itself ? "on demand" : a.kind === "person" ? "by a person" : "not run here")}</Table.Td>
                  <Table.Td num className="nowrap" data-use="cost" title={u.cost ? `${u.cost}, over ${u.ai_runs} runs` : ""}>
                    {costText(u, a)}{u.cost && u.cost !== "reported" && <Muted> est.</Muted>}
                  </Table.Td>
                  {nums.map(([key, , , v, text]) => <Table.Td key={key} num data-use={key}>{text(v(u))}</Table.Td>)}
                </Table.Row>
                {x && <tr className="exception-why"><td colSpan={span}>{x[1]}</td></tr>}
              </Fragment>
            );
          })}
        </Table.Body>
      ))}
      <Table.Body className="total">
        <tr data-total="">
          <td><b>total</b></td><td className="muted">over the window</td>
          <td className="num">{String(all.reduce((s, a) => s + (a.runs_itself ? a.runs || 0 : 0), 0))}</td><td /><td />
          <td className="num nowrap" data-use="cost">{spent ? usd(spent) + (gap && ` + ${gap}`) : gap || "$0: no AI cost recorded"}</td>
          {nums.map(([key, , , , text, total]) => <td key={key} className="num" data-use={key}>{text(total())}</td>)}
        </tr>
      </Table.Body>
    </Table>
  );
}

/** The daemons' note: what they are, and how their CPU and memory are counted. */
export const DaemonsNote = () => (
  <Note>Long-lived processes the blocks' runs and the sensors' readings are handed to. Their CPU and memory are the process's, sampled; an item's run is charged its wall time only.</Note>
);

/** The long-lived runners, as the engine last saw them: state, users, restarts, last line, what is in flight. */
export function DaemonsTable({ daemons }: { daemons: Record<string, any> }) {
  const ds = Object.entries(daemons || {});
  if (!ds.length) return <p className="muted">No daemons in the model.</p>;
  return (
    <Table caption="Daemons">
      <Table.Head>
        {["daemon", "state", "serves", "restarts", "last line", "in flight", "CPU", "memory"].map((c, i) => <Table.Th key={c} num={i > 2}>{c}</Table.Th>)}
      </Table.Head>
      <Table.Body>
        {ds.map(([n, d]) => (
          <tr key={n} data-daemon={n}>
            <td className="nowrap" title={d.run || ""}><AppLink to={itemHref(`ergostat.daemon/${n.replace(/#[^#]*$/, "")}`)}><b>{n}</b></AppLink></td>
            <td title={d.why || ""}><span className={d.state === "running" ? "s-holding" : "s-off"}>{d.state}</span>{d.alarm && <span className="s-off" title={d.alarm.why}> alarm</span>}</td>
            <td className="muted">{(d.users || []).length > 3 ? `${d.users.length} parts` : (d.users || []).join(", ")}</td>
            <td className="num" title={`${d.restarts_total} in all`}>{String(d.restarts)}</td>
            <td className="num nowrap">{d.last_line ? ago(d.last_line) : "–"}</td>
            <td className="num">{`${d.in_flight} of ${d.concurrency}`}</td>
            <td className="num">{cpuText(d.cpu)}</td>
            <td className="num">{bytesText(d.memory)}</td>
          </tr>
        ))}
      </Table.Body>
    </Table>
  );
}
