import { Fragment, type ReactNode } from "react";
import { AppLink } from "../../components";
import { dur, recordedShort } from "../../lib/format";

/* Small parts the Goals and Agents pages share (missing from components/): a definition list that leaves out empty
   values, and a link to an agent's page. */

export function Dl({ rows, className }: { rows: [ReactNode, ReactNode][]; className?: string }) {
  const kept = rows.filter(([, v]) => v != null && v !== "" && v !== false);
  if (!kept.length) return null;
  return (
    <dl className={className}>
      {kept.map(([k, v], i) => <Fragment key={i}><dt>{k}</dt><dd>{v}</dd></Fragment>)}
    </dl>
  );
}

export const agentHref = (n: string) => `/agent/${encodeURIComponent(n)}`;
export const AgentA = ({ name }: { name: string }) => <AppLink to={agentHref(name)} className="agent-link">{name}</AppLink>;

/** The window, as the header measures it: "over the 3m recorded" or "over the last 1h". */
export function windowNote(st: any): string {
  const recorded = recordedShort(st);
  return st?.window ? (recorded != null ? `over the ${dur(recorded)} recorded` : `over the last ${dur(st.window)}`) : "";
}
