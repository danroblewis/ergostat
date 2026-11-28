import type { ReactNode } from "react";
import { ApiError } from "../../../lib/api";
import { AgentsTable, CostNote, DaemonsNote, DaemonsTable, LadderLine } from "../../agents/AgentsLists";
import { Definition, LogTail, logFile, Place, RUNG_SECTION, Runs, rungOf, WhatItIs } from "../../agents/AgentSections";
import { PanelFrame } from "../../charts/PanelView";
import { ancillaryMark, scopedBy, type Scoped } from "../../../lib/scoped";
import { scopeHref } from "../../../lib/hrefs";
import { useDashboards } from "../../../state/dashboards";
import { AppLink, Async, ErrorNote, Loading } from "../../ui";
import type { PanelBodyProps, PanelDef, PanelKind } from "../types";
import { usePanelApi } from "../usePanelApi";
import { asQueryPanel } from "./core";

/* The agents group's kinds of panel (each also declared in ergostat/spec/dashboards.py, its agents block): the Agents
   page's ladder, agents table and daemons, and each section of an agent's own page, for the agent its `agent` names. */

/** Whether an answer says the agent is not the model's (its endpoint's 404). */
export const noAgent = (e: Error | null | undefined) => !!e && (e instanceof ApiError && e.status === 404 || /not in this snapshot/.test(e.message));

/** The agents a system contains (`system`), or every one. */
const mine = (d: Record<string, any>, s: Scoped | null) => (s ? Object.fromEntries(Object.entries(d).filter(([n]) => s.has("agents", n))) : d);

function LadderBody({ def, every, refreshKey }: PanelBodyProps) {
  const got = usePanelApi<Record<string, any>>("agents", {}, every, refreshKey);
  const s = scopedBy(useDashboards().table, def.system);
  return <Async state={got}>{(d) => <LadderLine agents={mine(d, s)} />}</Async>;
}

function AgentsBody({ def, every, refreshKey }: PanelBodyProps) {
  const got = usePanelApi<Record<string, any>>("agents", {}, every, refreshKey);
  const s = scopedBy(useDashboards().table, def.system);
  return (
    <div className="panel-table">
      <Async state={got}>{(d) => <><AgentsTable agents={mine(d, s)} caption={def.title || "Agents, by rung"}
        mark={(n) => ancillaryMark(s, "agents", n)} label={s ? (n) => s.label("agents", n) : undefined} /><CostNote /></>}</Async>
    </div>
  );
}

function DaemonsBody({ every, refreshKey }: PanelBodyProps) {
  const got = usePanelApi<Record<string, any>>("daemons", {}, every, refreshKey);
  return <div className="panel-table"><DaemonsNote /><Async state={got}>{(d) => <DaemonsTable daemons={d} />}</Async></div>;
}

type Part = { a: any; name: string; def: PanelDef; every?: number | null; refreshKey?: unknown };

/** One section of an agent's page as a kind of panel: it asks /api/agents/AGENT, says when the model has no such
 *  agent, and takes its title from what the agent is when the declaration gives none. */
function agentKind(label: string, title: (a: any) => string, Part: (p: Part) => ReactNode): PanelKind {
  return {
    label, needs: "agent",
    Frame: ({ def, every, refreshKey, tools }) => {
      const name = String(def.agent || "");
      const got = usePanelApi<any>(name ? `agents/${encodeURIComponent(name)}` : null, {}, every, refreshKey);
      const a = got.data;
      const panel = asQueryPanel({ ...def, title: def.title || (a ? title(a) : label) });
      let body: ReactNode;
      if (!name) body = <p className="note lvl-error">This panel names no agent (agent:).</p>;
      else if (a === undefined) {
        body = noAgent(got.error) ? <p className="muted no-agent">{`No agent ${name} in the model · `}<AppLink to={scopeHref("", "agents")}>every agent</AppLink></p>
          : got.error ? <ErrorNote error={got.error} /> : <Loading />;
      } else body = <>{got.error && !noAgent(got.error) && <ErrorNote error={got.error} />}<Part a={a} name={name} def={def} every={every} refreshKey={refreshKey} /></>;
      return <PanelFrame panel={panel} tools={tools} className={`panel-kind-${def.panel} agent-part`}>{body}</PanelFrame>;
    },
  };
}

function WhatPart({ a, name, every, refreshKey }: Part) {
  const fs = usePanelApi<any>(`agents/${encodeURIComponent(name)}/files`, {}, every, refreshKey);
  return <WhatItIs a={a} files={fs.data?.files || []} />;
}

function PlacePart({ a, name, every, refreshKey }: Part) {
  const loops = usePanelApi<any>("loops", {}, every, refreshKey);
  return <Place a={a} name={name} loops={loops.data} />;
}

export const AGENTS: Record<string, PanelKind> = {
  ladder: { label: "The ladder: agents on each rung", Body: LadderBody },
  agents: { label: "Agents, by rung, with what their runs cost", Body: AgentsBody },
  daemons: { label: "Daemons", Body: DaemonsBody },
  "agent-what": agentKind("What an agent is", (a) => RUNG_SECTION[rungOf(a) ?? 5] || "Its law", WhatPart),
  "agent-definition": agentKind("An agent's definition", () => "Its definition", ({ a }) => <Definition a={a} />),
  "agent-place": agentKind("An agent's place", () => "Its place", PlacePart),
  "agent-runs": agentKind("What an agent did", () => "What it did", ({ a, name, every, refreshKey }) => <Runs a={a} name={name} every={every} refreshKey={refreshKey} />),
  "agent-log": agentKind("An agent's log", (a) => `End of its log${logFile(a) ? `, ${logFile(a)}` : ""}`, ({ a }) => <LogTail a={a} />),
};
