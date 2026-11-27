import { useSend } from "../../hooks/useSend";

/* A projection's definition while its page is edited (SPEC §5a): a new one's start, and the draft tried on the record
   (POST /api/projections/try, ~500 ms after it last changed, the one in flight cancelled) for its check errors and the
   draft's id, which the page's panels are given so they draw the draft's objects. The workbench (workbench/) is the
   edit itself. */

export type TryReport = Record<string, any>;

/** A new projection's start: the events whose type starts with its name, no kinds of event yet. */
export const starter = (name: string) => `query: type.startswith('${name}.')\n`;

export function useTry(name: string, text: string | null, system: string) {
  const got = useSend<TryReport>("projections/try", text == null ? null : { name, yaml: text, system: system || undefined }, 500);
  return { report: text == null ? null : got.data, error: got.error, busy: got.busy };
}
