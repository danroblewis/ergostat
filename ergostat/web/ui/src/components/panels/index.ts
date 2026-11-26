/* Panels of every kind, the same on any page: a page made of panels is a dashboard. */
export { DashboardView } from "./DashboardView";
export { PanelBox } from "./PanelBox";
export { KINDS, asQueryPanel, paramsOf } from "./kinds/index";
export { normalizeDashboard, normalizePanel } from "./normalize";
export { endpointParams, usePanelApi } from "./usePanelApi";
export type { DashboardDef, PanelDef, PanelKind, PanelBodyProps } from "./types";
export { DeclaredDashboard, EVERY, Refresh, useDeclared } from "./Declared";
