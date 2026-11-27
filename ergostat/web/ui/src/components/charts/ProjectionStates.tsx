import { dur } from "../../lib/format";
import { Loading } from "../ui";
import { FlowChart } from "./FlowChart";

/** A projection's states over the window (items-flow, with its footprint's groups), as groups (waiting, working, stopped, done) or each state; and its cycle time. */
export function ProjectionStates({ flow, fp, all }: { flow: any; fp: any; all: boolean }) {
  if (!flow) return <Loading />;
  const any = Object.values(flow.counts || {}).some((c: any) => c.some((x: number) => x));
  if (!any) return <p className="muted">None of these items in the window.</p>;
  let states: string[] = flow.states, counts: Record<string, number[]> = flow.counts;
  if (!all && fp?.group) {
    const grouped: Record<string, number[]> = {};
    for (const [s, c] of Object.entries<number[]>(flow.counts)) {
      const g = fp.group[s] || s;
      grouped[g] = (grouped[g] || flow.times.map(() => 0)).map((x: number, i: number) => x + (c[i] || 0));
    }
    states = (fp.groups || Object.keys(grouped)).filter((g: string) => g in grouped);
    counts = grouped;
  }
  return (
    <div className="projection-flow">
      <FlowChart key={all ? "all" : "groups"} times={flow.times} states={states} counts={counts} height={140} />
      {flow.finished_total > 0 && (
        <p className="muted small">
          {flow.finished_total} finished in the window{flow.median != null ? `, the median took ${dur(flow.median)}` : ""}.
        </p>
      )}
    </div>
  );
}
