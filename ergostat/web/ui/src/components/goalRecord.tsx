import { fmt, stamp } from "../lib/format";
import { AppLink, StatusWord } from "./ui";

/* What a goal's record says of it in the window, from its loop's answer (GET /api/loops/NAME): its crossings, each a
   link to what the goal, its controller and its valves recorded from it to the next, and its controller's decisions,
   alike when only their numbers differ. The goal's side panel draws them, and so do the goal-crossings and
   goal-decisions panels. */

/** The crossings' heading: how many of how many are listed. */
export const crossingsTitle = (lp: any) =>
  `Crossings${lp.crossings_total > (lp.crossings?.length || 0) ? `, the newest ${lp.crossings.length} of ${lp.crossings_total}` : ""}`;

/** The goal's crossings (lp.crossings, oldest first as the answer gives them), newest first. */
export function GoalCrossings({ goal, lp }: { goal: string; lp: any }) {
  const cs: any[] = lp.crossings || [];
  const next = (i: number) => cs[i + 1]?.time ?? lp.until;
  return (
    <table className="crossings">
      <caption className="sr-only">{`The crossings of goal ${goal}, newest first`}</caption>
      <tbody>
        {cs.map((e, i) => [e, next(i)] as const).reverse().map(([e, to]) => (
          <tr key={e.id}>
            <td className="nowrap">
              <AppLink to={`/record?about=${encodeURIComponent(goal)}&from=${e.time}${to != null ? `&to=${to}` : ""}`}
                title="What the goal, its controller and its valves recorded from this crossing to the next">{stamp(e.time)}</AppLink>
            </td>
            <td><StatusWord status={e.type.split(".")[1]} /></td>
            <td className="num">{fmt(e.data.value)}</td>
            <td className="muted">{e.type === "loop.off" ? e.off_by_words || "" : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** The decisions' heading: how many. */
export const decisionsTitle = (lp: any) => `Decisions (${lp.decisions?.count ?? 0})`;

/** The controller's decisions in the window, by kind (lp.decisions), the commonest `most`, and a link to them in the
 *  Record. */
export function GoalDecisions({ goal, lp, most = 6 }: { goal: string; lp: any; most?: number }) {
  const kinds: [string, number][] = lp.decisions?.kinds || [];
  return (
    <>
      <div className="note">Alike when only their numbers differ.</div>
      <table className="decisions">
        <caption className="sr-only">{`The decisions of goal ${goal}'s controller, commonest first`}</caption>
        <tbody>{kinds.slice(0, most).map(([w, n], i) => (
          <tr key={i}><td className="num">{n}</td><td>{w.replaceAll("#", "N")}</td></tr>))}</tbody>
      </table>
      <p className="small">
        <AppLink to={`/record?item=${encodeURIComponent(goal)}&match=controller.decided${lp.since != null ? `&from=${lp.since}&to=${lp.until}` : ""}`}
          title="Each decision of its controller in the window, in the Record">Each one in the Record</AppLink>
      </p>
    </>
  );
}
