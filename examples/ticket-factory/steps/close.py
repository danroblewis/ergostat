"""close: the issue to Done (JIRA_DONE) with a comment saying what became of it, and the workspace given back.
Its cycle time (found to done) is recorded on it."""

import jira
import workspace
from act import act
from step import Move
from tf import conf, key_of, now


def run(ticket):
    f = ticket["fields"]
    key = key_of(ticket)
    hours = (now() - float(ticket.get("first") or now())) / 3600
    how = "merged" if f.get("merged") else f"not merged ({f.get('merge_note', '')})"
    act("jira.transition", key, "close", f"Move {key} to {conf('JIRA_DONE')}", jira.transition, key, conf("JIRA_DONE"))
    act("jira.comment", key, "close", f"Comment on {key}: what became of it", jira.comment, key,
        f"Done: {f.get('pr_url', '')} {how}. Cycle time {hours * 60:.1f} min; "
        f"{int(f.get('repings') or 0)} re-ping(s), {int(f.get('ci_failures') or 0)} CI failure(s), "
        f"AI cost ${float(f.get('ai_cost_usd') or 0):.4f}.")
    workspace.release(key, f["repo"])
    return Move({"done_at": now(), "cycle_hours": round(hours, 4)})
