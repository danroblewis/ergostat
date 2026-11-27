/* What a tab keeps while work is under way (sessionStorage: this tab only, gone when it closes), so that a reload, a
   remount or an address that lost its history state does not lose it: the projection workbench's draft, and that a
   projection at an address is a new one not yet saved. Every access may throw (storage off, full): then nothing is
   kept, and nothing breaks. */

export function keptGet<T>(key: string): T | null {
  try { const s = sessionStorage.getItem(key); return s == null ? null : (JSON.parse(s) as T); } catch { return null; }
}

export function keptSet(key: string, v: unknown): void {
  try { sessionStorage.setItem(key, JSON.stringify(v)); } catch { /* not kept */ }
}

export function keptDrop(...keys: string[]): void {
  for (const k of keys) { try { sessionStorage.removeItem(k); } catch { /* nothing kept */ } }
}

/** Where a projection's draft is kept: its YAML text (and as it was when editing began), and the workbench's steps. */
export const draftKey = (system: string, projection: string) => `ergostat:workbench:${system}:${projection}`;
export const stepsKey = (system: string, projection: string) => `ergostat:workbench-steps:${system}:${projection}`;
/** A new projection (the nav bar's +) at an address, until it is saved or cancelled. */
export const newProjectionKey = (pathname: string) => `ergostat:new-projection:${pathname}`;
