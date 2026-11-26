import { useEffect, useRef } from "react";
import { AppLink, ErrorNote, Loading, Meta, Page, Rung } from "../../components";
import { engagedText } from "../../components/agents/agentParts";
import { noSpec, Serves } from "../../components/agents/AgentSections";
import { noAgent } from "../../components/panels/kinds/agents";
import { PanelBox } from "../../components/panels/PanelBox";
import { useApi } from "../../hooks/useApi";
import { AGENT_PANELS } from "../../lib/pages";

/* An agent's own page (/agent/NAME, agent.js pageAgent): a built-in dashboard of the agents group's panels (what it
   is, by its rung; its definition as written; its place in the model; what it did; the end of its log), each for the
   agent the address names. The page keeps its own head: the Meta row and its description. Each section is an anchor. */

const EVERY = 4000;

export default function AgentPage({ name }: { name: string }) {
  const path = `agents/${encodeURIComponent(name)}`;
  const ag = useApi<any>(path, {}, { every: EVERY });
  const loops = useApi<any>("loops", {}, { every: EVERY });
  const scrolled = useRef(false);
  useEffect(() => {
    if (!ag.data || scrolled.current) return;
    scrolled.current = true;
    if (location.hash.length > 1) requestAnimationFrame(() => document.getElementById(location.hash.slice(1))?.scrollIntoView());
  }, [ag.data]);

  if (ag.data === undefined) {
    if (noAgent(ag.error)) {
      return <Page title={name}><p className="no-agent">{`no agent ${name} · `}<AppLink to="/agents">every agent</AppLink></p></Page>;
    }
    return <Page title={name}>{ag.error ? <ErrorNote error={ag.error} /> : <Loading />}</Page>;
  }
  const a = ag.data, sp = a.spec, r = a.rung ?? a.agent?.rung;
  const jump = (id: string, text: string) => <a href={`#${id}`} onClick={(ev) => { ev.preventDefault(); document.getElementById(id)?.scrollIntoView(); }}>{text}</a>;
  const pl = a.place || {};
  const panels = AGENT_PANELS.filter((d) => d.panel !== "agent-log" || a.log?.length).map((d) => ({ ...d, agent: name }));
  return (
    <Page title={name} className="agent-page">
      <Meta rows={[
        ["Kind", <span title={sp?.rung_why || ""}><Rung rung={r} retired={r == null || r > 5} /></span>],
        ["Machine", sp?.machine ? `${sp.machine.name}${sp.machine.model ? `, ${sp.machine.model}` : ""}` : null],
        ["System", pl.system],
        ["Serves", loops.data ? <Serves a={a} loops={loops.data} /> : null],
        ["Engaged", engagedText(a)],
        ["Mode", pl.mode],
        ["Defined at", sp?.where ? jump("its-definition", `${sp.where.file}:${sp.where.line}`) : sp?.implied ? jump("its-definition", "not written") : null],
      ]} />
      {ag.error && <ErrorNote error={ag.error} />}
      {a.agent?.description && <p className="muted">{noSpec(a.agent.description)}</p>}
      <div className="panel-grid">
        {panels.map((d) => (
          <section key={d.id} id={d.id} className={`panel-${d.size}`}><PanelBox def={d} every={EVERY} /></section>
        ))}
      </div>
    </Page>
  );
}
