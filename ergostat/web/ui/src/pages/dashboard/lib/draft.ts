import { normalizeDashboard, type DashboardDef } from "../../../components/panels";

/* This browser's draft of a dashboard, kept in its storage under the project's name. */
const keyOf = (name: string) => `ergostat.dashboard.${name}`;

export function stored(name: string): DashboardDef | null {
  try {
    const d = JSON.parse(localStorage.getItem(keyOf(name)) || "null");
    return d && Array.isArray(d.panels) ? normalizeDashboard(d) : null;
  } catch { return null; }
}
export function store(name: string, d: DashboardDef | null): void {
  try { if (d) localStorage.setItem(keyOf(name), JSON.stringify(d)); else localStorage.removeItem(keyOf(name)); } catch { /* kept for this visit only */ }
}

