import { Fragment } from "react";
import { AppLink, Async, Muted, Note, Page, Table } from "../../components";
import { useApi } from "../../hooks/useApi";
import { ago, bytesText, costText, cpuText, op, tokensText, usd } from "../../lib/format";
import { RUNG_HINT, RUNG_NAMES } from "../../lib/rung";
import { useStatus } from "../../state/status";
import { WINDOW_WORDS, useTime } from "../../state/time";
import { agentHref, windowNote } from "../goals/parts";
import { exception, lastText, rolesText } from "./agentParts";

/* Agents (pages.js pageAgents): the ladder, one list by rung from the most general agent to none, what each costs in
   the window, and the daemons. */

const COLS = [...RUNG_NAMES, "retired"] as string[];
type Num = [key: string, head: string, title: string, cell: (u: any) => number | null | undefined, text: (n: any) => string, total: () => number];

export default function AgentsPage() {
  const agents = useApi<Record<string, any>>("agents", {}, { every: 3000 });
  const daemons = useApi<Record<string, any>>("daemons", {}, { every: 3000 });
  const { status } = useStatus();
  const { since } = useTime();
  const w = WINDOW_WORDS[since] ? `over the ${WINDOW_WORDS[since].toLowerCase()}` : windowNote(status);
  return (
    <Page title="Agents">
      <Async state={agents}>{(data) => <Ladder agents={data} />}</Async>
      <Note>
        {`What the runs cost${w ? ", " + w : ""}: dollars their AI sessions cost (as Claude Code reported them; "est." where only tokens were known and a price table priced them), their tokens, the CPU time of each run's processes (user and system), and the most memory one run held. Open an agent for what it is and its history, run by run.`}
      </Note>
      <Daemons daemons={daemons.data} />
    </Page>
  );
}

function Ladder({ agents }: { agents: Record<string, any> }) {
  const of = (i: number) => Object.entries(agents).filter(([, a]) => a.rung === i);
  const tally: Record<string, number> = {};
  for (const a of Object.values(agents)) {
    const x = exception(a);
    if (x) { const k = x[0].startsWith("behind") ? "behind schedule" : x[0]; tally[k] = (tally[k] || 0) + 1; }
  }
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
  return (
    <>
      <div className="ladder-line">
        {COLS.map((k, i) => (
          <span key={k} className="step" data-kind={k} title={RUNG_HINT[i]}>{of(i).length ? <b>{of(i).length}</b> : "0"}{` ${k}`}</span>
        ))}
        <Muted>most general → most specific</Muted>
        {Object.entries(tally).map(([k, n]) => <span key={k} className="exception">{`${n} ${k}`}</span>)}
      </div>
      <Table caption="Agents, by rung">
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
                  <Table.Row to={agentHref(name)}>
                    <Table.Td className="nowrap">
                      <AppLink to={agentHref(name)} className="agent-link"><b>{name}</b></AppLink>
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
                    <Table.Td num>{String(a.runs ?? "")}</Table.Td>
                    <Table.Td className="nowrap muted">{lastText(a)}</Table.Td>
                    <Table.Td className="muted">{a.schedule || a.every || (a.leased ? "on demand, per item (leased)" : a.runs_itself ? "on demand" : a.kind === "person" ? "by a person" : "not run here")}</Table.Td>
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
    </>
  );
}

function Daemons({ daemons }: { daemons: Record<string, any> | undefined }) {
  const ds = Object.entries(daemons || {});
  if (!ds.length) return null;
  return (
    <div>
      <h3>Daemons</h3>
      <Note>Long-lived processes the blocks' runs and the sensors' readings are handed to. Their CPU and memory are the process's, sampled; an item's run is charged its wall time only.</Note>
      <Table caption="Daemons">
        <Table.Head>
          {["daemon", "state", "serves", "restarts", "last line", "in flight", "CPU", "memory"].map((c, i) => <Table.Th key={c} num={i > 2}>{c}</Table.Th>)}
        </Table.Head>
        <Table.Body>
          {ds.map(([n, d]) => (
            <tr key={n} data-daemon={n}>
              <td className="nowrap" title={d.run || ""}><b>{n}</b></td>
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
    </div>
  );
}
