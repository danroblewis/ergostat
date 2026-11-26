import { itemPath } from "./routes";

/* The page's addresses, built in one place: every link to an item, a kind, an agent or a part of the diagram. */

/** An item's page: /KIND/REST (lib/routes.ts), else /item/ID (one on a remote, or no kind of this model's matches). */
export const itemHref = (id: string, remote?: string) =>
  remote ? `/item/${encodeURIComponent(id)}?remote=${encodeURIComponent(remote)}` : itemPath(id) || `/item/${encodeURIComponent(id)}`;
/** A kind's page: /KIND. */
export const kindHref = (name: string, q = "") => `/${encodeURIComponent(name)}${q ? `?${q}` : ""}`;
export const agentHref = (name: string) => `/agent/${encodeURIComponent(name)}`;

/** The diagram, drawn the way asked: a view, a system, or only what an item or a kind passed through (the Process
 *  view: only these kinds, `kinds`). */
export function diagramHref(at: { view?: "dynamics" | "blocks" | "process"; system?: string; item?: string; kind?: string; around?: string; kinds?: string } = {}) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(at)) if (v && !(k === "view" && v === "dynamics")) q.set(k, v);
  const s = q.toString();
  return `/diagram${s ? `?${s}` : ""}`;
}

/** A Diagram address read back: what diagramHref writes (a dashboard's diagram panel keeps its address). */
export function diagramOf(address: string): { view: "dynamics" | "blocks" | "process"; system: string; item: string; kind: string; around: string; kinds: string } {
  const q = new URLSearchParams(address.split("?")[1] || "");
  const v = q.get("view");
  return {
    view: v === "blocks" || v === "process" ? v : "dynamics",
    system: q.get("system") || "", item: q.get("item") || "", kind: q.get("kind") || "", around: q.get("around") || "",
    kinds: q.get("kinds") || "",
  };
}
