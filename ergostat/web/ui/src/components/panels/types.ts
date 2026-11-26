import type { ReactNode } from "react";

/* A panel as a dashboard declares it: the same shape on the page, in this browser's draft and in the model's
   `dashboards:` (SPEC §4f): its kind (`panel`), its words, its size, and exactly the parameters its endpoint takes,
   by the same names. `id` is the page's own handle on it (a draft's), never written to the model. */
export type PanelDef = {
  panel: string;
  id?: string;
  title?: string;
  note?: string;
  size?: "s" | "m" | "l" | "full";
  tall?: boolean;
  [param: string]: any;
};

export interface DashboardDef {
  title: string;
  description?: string;
  /** the window it opens with, like "7d" (none: the page's) */
  since?: string | null;
  panels: PanelDef[];
}

/** What a panel's body is drawn from: its declaration, and the page's refresh. */
export interface PanelBodyProps {
  def: PanelDef;
  /** ms between asking again (none: once) */
  every?: number | null;
  /** changes when the page asks every panel again now */
  refreshKey?: unknown;
}

/** One kind of panel: what it is called in the editor, what it needs, and what draws it. A kind whose `Frame` is
 *  set draws its own frame (the query and diagram panels); the rest draw a body inside the shared one. */
export interface PanelKind {
  label: string;
  /** the parameter it cannot do without (as the model's check says: NEEDS) */
  needs?: string;
  Body?: (p: PanelBodyProps) => ReactNode;
  Frame?: (p: PanelBodyProps & { tools?: ReactNode }) => ReactNode;
}
