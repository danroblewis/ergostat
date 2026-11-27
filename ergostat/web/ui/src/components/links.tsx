import type { ReactNode } from "react";
import { agentHref, itemHref, projectionHref } from "../lib/hrefs";
import { AppLink } from "./ui";

/* Links to the things ergostat shows, the same on every page: an agent, an item (here or on a remote), a projection. */

export const AgentLink = ({ name, children }: { name: string; children?: ReactNode }) =>
  <AppLink to={agentHref(name)} className="agent-link">{children ?? name}</AppLink>;

/* the ids that may be opened on a remote: as remote/items.py's openable, an allowlist (/-separated segments, no "..") */
const REMOTE_ID = /^[A-Za-z0-9_][A-Za-z0-9_.:@#+=-]*(\/[A-Za-z0-9_][A-Za-z0-9_.:@#+=-]*)*$/;

/** An item's link: "–" for none; one on a remote only when its id is one a remote may open, else its id unlinked. */
export function ItemLink({ id, remote, className, children }: { id?: string | null; remote?: string; className?: string; children?: ReactNode }): ReactNode {
  if (!id) return "–";
  if (remote && !(id.length <= 200 && REMOTE_ID.test(id) && !id.includes(".."))) return id;
  return <AppLink to={itemHref(id, remote)} className={className}>{children ?? id}</AppLink>;
}

export const ProjectionLink = ({ name, children, className }: { name: string; children?: ReactNode; className?: string }) =>
  <AppLink to={projectionHref(name)} className={className}>{children ?? name}</AppLink>;
