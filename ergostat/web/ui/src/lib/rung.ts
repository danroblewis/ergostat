/* An agent's rung: its kind, always said in words and a letter, never by colour alone (invariant 4). */
export const RUNG_NAMES = ["person", "ai", "narrow-ai", "decision", "program", "rule"] as const;
export const RUNG_HINT = [
  "the most general agent", "a universal AI agent", "an AI agent with one job", "a short model call with fixed answers",
  "deterministic code", "a threshold or a table", "the work designed out",
];
export const RUNG_LETTER = ["H", "A", "N", "D", "P", "R", "–"];
export const rungName = (r: number | null | undefined): string => (r == null ? "?" : RUNG_NAMES[r] ?? "retired");
