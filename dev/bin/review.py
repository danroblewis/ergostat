"""reviewer: takes a gap at built, under a lease, and judges its branch: a fresh session that is given the definition
of done, the GAPS entry, the rules, the earlier findings and the diff, and never the implementor's reasoning. It runs
in a read-only worktree of its own (<worktrees>/.review/<branch>, detached at the branch's head), with read tools only.

Before the session, the mechanical gates: the definition file committed first and unchanged since (but for a "Where it
stopped" section), and the size budget. A gate that fails is a blocking finding.

It records a `review` item (review/<branch>-<n>: its verdict, blocking and non-blocking findings, the context it was
given, its cost), then moves the gap: approved (merge), back to fix with the findings, or parked. The kill rule: the
second failed gate (a fix verdict, or a real failure in the queue) parks the gap with where it stopped, written into
its definition file."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import agents  # noqa: E402
import brief  # noqa: E402
import fac  # noqa: E402
import pools  # noqa: E402

VERDICT_EVENT = {"merge": "review.approved", "fix": "review.sent-back", "park": "review.parked"}
VERDICT = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


def gates(cfg: dict, wt: Path, branch: str, base: str, continued: bool = False) -> tuple[list[str], str]:
    """The mechanical gates: (blocking findings, the definition as committed first). The branch's own commits are
    its first-parent line (main merged in is not the branch's); a continued branch's merge base must be main itself."""
    rel = f"{fac.DEFS}/{branch}.md"
    found = []
    own = ("--first-parent", "--topo-order", "--reverse")
    commits = fac.git(wt, "rev-list", *own, f"{base}..HEAD").split()
    touched = fac.git(wt, "log", *own, "--format=%H", f"{base}..HEAD", "--", rel).split()
    on_base = fac.git_ok(wt, "cat-file", "-e", f"{base}:{rel}")
    if not on_base and (not touched or not commits or touched[0] != commits[0]):
        found.append(f"gate 1: {rel} is not the branch's first commit")
    if continued and fac.git(wt, "merge-base", base, "HEAD", check=False) != fac.git(wt, "rev-parse", base):
        found.append(f"gate 1: the continued branch's merge base is not current main ({base}): main is not merged in")
    first = fac.git(wt, "show", f"{touched[0] if touched else base}:{rel}", check=False)
    now = (wt / rel).read_text() if (wt / rel).is_file() else ""
    cut = lambda t: re.split(r"^## Where it stopped", t, flags=re.M)[0].strip()  # noqa: E731
    if first and cut(first) != cut(now):
        found.append(f"gate 1: {rel} was changed after its first commit (other than a 'Where it stopped' section)")
    return found, first or now


def verdict(said: str) -> dict:
    blocks = VERDICT.findall(said)
    if not blocks:
        raise RuntimeError("the reviewer gave no fenced JSON verdict")
    v = json.loads(blocks[-1])
    if v.get("verdict") not in ("merge", "fix", "park"):
        raise RuntimeError(f"the reviewer's verdict is not merge, fix or park: {v.get('verdict')!r}")
    return {"verdict": v["verdict"], "blocking": [str(x) for x in v.get("blocking") or []],
            "non_blocking": [str(x) for x in v.get("non_blocking") or []],
            "where_it_stopped": str(v.get("where_it_stopped") or "")}


def park(cfg: dict, gap: dict, why: str, by: str, where: str = "review") -> None:
    """Where it stopped, written into the definition file on the gap's branch (a commit this program makes in a clone
    of its own, pushed to the drop), then the gap parked."""
    branch = fac.branch_of(gap)
    rel = f"{fac.DEFS}/{branch}.md"
    d = agents.drop(cfg)
    if fac.git_ok(d, "rev-parse", "--verify", "-q", f"refs/heads/{fac.git_branch(branch)}"):
        _, work = agents.clone(cfg, branch, "park")
        if (work / rel).is_file():
            with (work / rel).open("a") as fh:
                fh.write(f"\n## Where it stopped\n\nParked by the factory ({by}, {time.strftime('%Y-%m-%d %H:%M')})."
                         f"\n\n{why.strip()}\n")
            fac.git(work, "-c", "user.name=factory", "-c", "user.email=factory@localhost", "commit", "-q", "-am",
                    f"{branch}: where it stopped\n\n{fac.TRAILER}")
            agents.publish(cfg, work, branch)
    fac.say("gap.parked", gap["id"], parked_at=time.time(), where_it_stopped=why[:4000], parked_by=by, parked_in=where)


def main() -> int:
    fac.stop_on_term()
    cfg = fac.config()
    given = fac.read_input()
    began = time.time()
    try:
        return judge(cfg, given["item"], began)
    except agents.Refused as e:
        fac.nack(str(e), after="1h", count=False)
        return 0
    except Exception:  # noqa: BLE001 - parked on its last attempt, never a dead letter
        return fac.guarded(given, began, "review_hours", lambda why: park(cfg, given["item"], why, "reviewer"))


def next_review(branch: str) -> int:
    """The number of a new review of the branch: past the highest review/<branch>-N in the record, so a gap that
    continues a branch already reviewed (or its fix rounds) never reuses a parked gap's review item. A record that
    cannot be read raises (fac.items)."""
    got = [re.fullmatch(rf"review/{re.escape(branch)}-(\d+)", str(r.get("id"))) for r in fac.items("review")]
    return max([int(m[1]) for m in got if m] or [0]) + 1


def judge(cfg: dict, gap: dict, began: float) -> int:
    f = gap["fields"]
    refused = fac.may_spend(cfg, float(cfg["ai"]["reviewer_session_usd"]))
    if refused:
        fac.nack(f"budget: {refused}", after="1h", count=False)
        return 0
    if not pools.my_turn(cfg, "reviewer", "reviewer", gap["id"]):
        fac.nack("the reviewer pool is full (run/pools.json): waits its turn", after="5m", count=False)
        return 0
    branch, base = fac.branch_of(gap), f"origin/{cfg['git']['base']}"       # (in the clone made from the drop)
    n = int(f.get("reviews_n") or 0) + 1
    rid = f"review/{branch}-{next_review(branch)}"
    fac.say("gap.review-started", review_at=began, reviews_n=1)
    head = str(f.get("head") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise RuntimeError(f"{gap['id']} has no built head to review")
    home, wt = agents.clone(cfg, branch, "reviewer", at=head)
    blocking, definition = gates(cfg, wt, branch, base, continued=bool(f.get("continues")))
    net, budget = fac.net_lines(wt, base, "HEAD"), fac.budget_of(definition)
    if net > budget and not re.search(r"over.*reason|reason.*over", definition, re.I | re.S):
        blocking.append(f"size: {net} net lines of core code against a budget of {budget}, with no reason written")
    diff = fac.git(wt, "diff", f"{base}...HEAD")
    if len(diff) > brief.DIFF_MOST:
        diff = (fac.git(wt, "diff", "--stat", f"{base}...HEAD") + "\n\n(the diff is too long to give whole: read it"
                f" with `git diff {base}...HEAD -- FILE`)")
    text, context = brief.assemble(
        cfg, "reviewer", gap, wt, definition=definition, diff=f"```diff\n{diff}\n```", net_lines=net,
        gates="; ".join(blocking) or "all passed")
    context["brief"] = brief.save(cfg, "reviewer", gap, text)
    try:
        got = fac.session(cfg, "reviewer", text, wt)
    except fac.OverBudget as e:
        fac.nack(f"budget: {e}", after="1h", count=False)
        return 0
    v = verdict(str(got.get("result", "")))
    v["blocking"] = blocking + v["blocking"]
    if v["blocking"] and v["verdict"] == "merge":
        v["verdict"] = "fix"
    cost = round(float(got.get("total_cost_usd") or 0), 4)
    fac.say("review.written", rid, gap=gap["id"], round=n, written_at=time.time(), **v, context=context, ai_cost_usd=cost,
            head=head, net_lines=net, budget=budget)
    fac.say(VERDICT_EVENT[v["verdict"]], rid, gap=gap["id"])
    record = dict(reviews=[rid], contexts=[context], ai_cost_usd=cost,
                  review_hours=round((time.time() - began) / 3600, 3))
    failed = int(f.get("failed_gates") or 0) + (v["verdict"] == "fix")
    if v["verdict"] == "merge":
        fac.say("gap.approved", approved_at=time.time(), approved_by="review", first_pass=n == 1, reviewed_head=head,
                **record)
    elif v["verdict"] == "park" or failed >= fac.kill_after(cfg):
        why = v["where_it_stopped"] or f"Failed its gates {fac.kill_after(cfg)} times (the kill rule). Blocking findings:\n" + "\n".join(
            f"- {b}" for b in v["blocking"])
        fac.say("gap.measured", failed_gates=int(v["verdict"] == "fix"), findings=v["blocking"], **record)
        park(cfg, gap, why, rid)
    else:
        fac.say("gap.sent-back", sent_back_by="review", findings=v["blocking"], failed_gates=1, fix_rounds=1,
                first_pass=False, **record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
