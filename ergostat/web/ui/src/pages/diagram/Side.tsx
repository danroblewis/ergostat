import { AppLink, Fold } from "../../components";
import { ControlLoops, FeedbackLoops, feedbackCount, Legend, LEGEND_TYPE } from "../../components/Attention";
import { ago } from "../../lib/format";
import { projectionHref } from "../../lib/hrefs";

/* The list beside the diagram (diagram.js's renderSide): only what reads the diagram: how to read the drawing (legend),
   then the view's own list (feedback-loops, control-loops, and the process map's projections). What asks for the
   owner is elsewhere: decisions on the Inbox, the goals off, the model's housekeeping and suggestions on Goals. */

export function Side({ g, view, onGoal, onPick }: { g: any; view: string; onGoal: (goal: string) => void; onPick: (n: any) => void }) {
  const loops = Object.keys(g?.loops || {});
  return (
    <>
      <Fold className="legend-box" open summary={<>How to read it<span className="muted"> · the {LEGEND_TYPE[view]}</span></>}>
        <Legend view={view} />
      </Fold>
      {view === "dynamics" && (
        <Fold className="loops" summary={<>Feedback loops <span className="muted">{feedbackCount(g)}</span></>}>
          <FeedbackLoops g={g} />
        </Fold>
      )}
      {view === "blocks" && (
        <Fold className="loops" summary={<>Control loops <span className="muted">{loops.length}</span></>}>
          <ControlLoops g={g} onGoal={onGoal} />
        </Fold>
      )}
      {view === "process" && (
        <Fold className="loops" open summary={<>Projections <span className="muted">{(g?.projections || []).length}</span></>}>
          {(g?.projections || []).map((k: any) => (
            <div key={k.name}><AppLink to={projectionHref(k.name)}>{k.name}</AppLink> <span className="muted">{k.items} item{k.items === 1 ? "" : "s"} · {k.by}</span></div>
          ))}
          {g?.since && <p className="muted small">since {ago(g.since)}{g.capped ? ", capped" : ""}</p>}
          {(g?.nodes || []).filter((n: any) => n.now).map((n: any) => (
            <div key={n.id}><button type="button" className="name" onClick={() => onPick(n)}>{n.label}</button> <span className="muted">now {n.now}</span></div>
          ))}
        </Fold>
      )}
    </>
  );
}
