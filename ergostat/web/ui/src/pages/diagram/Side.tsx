import { AppLink, Fold } from "../../components";
import { Attention, ControlLoops, FeedbackLoops, feedbackCount, Legend, LEGEND_TYPE } from "../../components/Attention";
import { ago } from "../../lib/format";
import { useStatus } from "../../state/status";

/* The list beside the diagram (diagram.js's renderSide), drawn from the attention panels' components: what waits for
   the owner, how to read the drawing (legend), the goals off, the model's housekeeping, suggestions (attention), then
   the view's own list (feedback-loops, control-loops, and the process map's kinds of item). */

export function Side({ g, view, onGoal, onPick }: { g: any; view: string; onGoal: (goal: string) => void; onPick: (n: any) => void }) {
  const { status: st } = useStatus();
  const all: any[] = g?.attention || st?.attention || [];
  const loops = Object.keys(g?.loops || {});
  return (
    <>
      <Attention attention={all} status={st} show={["waiting"]} onGoal={onGoal} />
      <Fold className="legend-box" open summary={<>How to read it<span className="muted"> · the {LEGEND_TYPE[view]}</span></>}>
        <Legend view={view} />
      </Fold>
      <Attention attention={all} status={st} show={["off", "housekeeping", "suggestions"]} onGoal={onGoal} />
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
        <Fold className="loops" open summary={<>Kinds of item <span className="muted">{(g?.kinds || []).length}</span></>}>
          {(g?.kinds || []).map((k: any) => (
            <div key={k.name}><AppLink to={`/items/${encodeURIComponent(k.name)}`}>{k.name}</AppLink> <span className="muted">{k.items} item{k.items === 1 ? "" : "s"} · {k.by}</span></div>
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
