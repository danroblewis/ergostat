import { crossingsTitle, decisionsTitle, GoalCrossings, GoalDecisions } from "./goalRecord";
import { GoalControlBox, GoalParts, GoalRunbook } from "./GoalParts";
import { ItemLink } from "./links";
import { AppLink, Async, StatusWord } from "./ui";
import { useApi } from "../hooks/useApi";
import { fmt, op, stamp } from "../lib/format";
import { exceptional, goalWord } from "../lib/goals";

/* A goal's detail, in the side panel (details.js openLoopNow), composed of the goal panels' parts (GoalParts.tsx): its
   runbook (four lines), the remedy and its numbers, its parts along the loop, what breaks it, then its control loop
   (control.js): the process identified, its controller, and the proposals the owner accepts or dismisses; then its
   crossings and decisions. Not ported: its scope charts and the forecast ahead. */

export function GoalDetail({ name }: { name: string }) {
  const lp = useApi<any>(`loops/${encodeURIComponent(name)}`, {}, { every: 4000 });
  return (
    <Async state={lp} what="Goal">
      {(lp) => {
        const word = goalWord(lp);
        const next = (i: number) => lp.crossings[i + 1]?.time ?? lp.until;
        return (
          <>
            <div className="kind">{lp.open_loop ? "Goal, open loop" : "Goal"}</div>
            <h2>{name}{exceptional(word) && <> <StatusWord status={word} /></>}</h2>
            <GoalRunbook name={name} lp={lp} />
            <GoalParts name={name} lp={lp} />
            {lp.breaking?.length > 0 && (
              <>
                <h3>{`Breaking it: ${lp.breaking_n} ${lp.per}${lp.breaking_n === 1 ? "" : "s"}`}</h3>
                <table><tbody>{lp.breaking.map((b: any, i: number) => {
                  const id = String(b.item ?? b.group);
                  return <tr key={i}><td>{id.includes("/") ? <ItemLink id={id} /> : id}</td><td className="num">{fmt(b.value)}</td></tr>;
                })}</tbody></table>
              </>
            )}
            <GoalControlBox goal={name} off={lp.off_share} />
            {(lp.gaps || []).map((g: string, i: number) => <p key={`g${i}`}><b className="lvl-warn">Cannot close: </b>{g}</p>)}
            {(lp.hints || []).filter((x: any) => x.about !== "loop").map((x: any, i: number) => <p key={`h${i}`}><b>Suggestion: </b>{op(x.says)}</p>)}
            {lp.crossings?.length > 0 && (
              <>
                <h3>{crossingsTitle(lp)}</h3>
                <GoalCrossings goal={name} lp={lp} />
              </>
            )}
            {lp.decisions?.count > 0 && (
              <>
                <h3>{decisionsTitle(lp)}</h3>
                <GoalDecisions goal={name} lp={lp} />
              </>
            )}
            <p><AppLink to={`/diagram?around=loop/${encodeURIComponent(name)}`}>Draw this loop alone</AppLink></p>
          </>
        );
      }}
    </Async>
  );
}
