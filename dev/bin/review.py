"""reviewer: takes a gap at built, under a lease, and judges its branch: a fresh session that is given the definition
of done, the GAPS entry, the rules, the earlier findings and the diff, and never the implementor's reasoning. It runs
in a read-only worktree of its own (<worktrees>/.review/<branch>, detached at the branch's head), with read tools only.

Before the session, the mechanical gates: the definition file on the branch and unchanged since its first commit (but
for a "Where it stopped" section; its position in the branch's history is not checked), and the size budget. A gate
that fails is a blocking finding.

It records a `review` item (review/<branch>-<n>: its verdict, blocking and non-blocking findings, the context it was
given, its cost), then moves the gap: approved (merge), back to fix with the findings, or parked. The kill rule: the
`[gates] kill_after`-th failed gate (a fix verdict, a conflict, or a real failure in the queue) parks the gap with
where it stopped, written into its definition file."""

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
import implement  # noqa: E402
import parks  # noqa: E402
import pools  # noqa: E402

VERDICT_EVENT = {"merge": "review.approved", "fix": "review.sent-back", "park": "review.parked"}
VERDICT = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


def gates(cfg: dict, wt: Path, branch: str, base: str, continued: bool = False,
          built_main: str = "", rel: str = "") -> tuple[list[str], str]:
    """The mechanical gates: (blocking findings, the definition as committed first). The definition must be on the
    branch (or on main) and unchanged since the first of the branch's commits that touched it, wherever that commit
    is in the branch's history. The branch's own commits are its first-parent line (main merged in is not the
    branch's). The definition is ``rel`` (fac.definition_file: for a continued gap, the file its `definition`
    names, first committed on the continued branch under whatever name that branch had), else
    `dev/records/<branch>.md` (or the old `docs/roadmap/overnight/<branch>.md` when the branch has only that). A
    continued branch must hold the main implement.py merged at its build (``built_main``), not the main of this moment: main moving between build and review is the merge queue's to
    settle (it merges and runs the suites again), never a failed gate. A ``built_main`` missing, or not on main,
    counts as the worst case: current main."""
    if not (re.fullmatch(r"[0-9a-f]{40}", built_main) and fac.git_ok(wt, "merge-base", "--is-ancestor", built_main, base)):
        built_main = fac.git(wt, "rev-parse", base)
    rel = rel or fac.definition_file({"id": f"gap/{branch}", "fields": {"branch": branch}}, wt)
    found = []
    own = ("--first-parent", "--topo-order", "--reverse")
    touched = fac.git(wt, "log", *own, "--format=%H", f"{base}..HEAD", "--", rel).split()
    on_base = fac.git_ok(wt, "cat-file", "-e", f"{base}:{rel}")
    if not on_base and not touched:      # its place in history is not a defect; its absence is (operator, 2026-11-20)
        found.append(f"gate 1: {rel} is not on the branch")
    if continued and not fac.git_ok(wt, "merge-base", "--is-ancestor", built_main, "HEAD"):
        found.append(f"gate 1: the continued branch does not hold main as of its build ({built_main[:12]}): main is "
                     "not merged in")
    first = fac.git(wt, "show", f"{touched[0] if touched else base}:{rel}", check=False)
    now = (wt / rel).read_text() if (wt / rel).is_file() else ""
    cut = lambda t: re.split(r"^## Where it stopped", t, flags=re.M)[0].strip()  # noqa: E731
    if first and cut(first) != cut(now):
        found.append(f"gate 1: {rel} was changed after its first commit (other than a 'Where it stopped' section)")
    return found, first or now


def appended(wt: Path, rel: str, first: str) -> str:
    """What the definition at the branch's HEAD (``wt/rel``) adds after its first-committed text ``first``: where the
    house rules put an overrun's reason ('Where it stopped'). A HEAD file that cannot be read, or that does not start
    with the first text (an edited definition), adds nothing, so a branch cannot write its reason by editing."""
    try:
        now = (wt / rel).read_text()
    except (OSError, UnicodeDecodeError):
        return ""
    first = first.strip()
    return now.lstrip()[len(first):] if first and now.lstrip().startswith(first) else ""


# An overrun's reason as the gate reads it: a line of its own that starts 'Overrun reason:' and says something after
# it. An allowlisted form, not words found anywhere, so free prose ('however ... reason'), a quoted size finding (the
# phrase falls mid-line there) and the factory's own park text do not pass for one.
OVER_REASON = re.compile(r"^(?:[-*][ \t]+)?(?:\*\*)?overrun reason:(?:\*\*)?[ \t]*\w[^\n]{8,}", re.I | re.M)


def stopped(text: str) -> str:
    """The 'Where it stopped' sections of ``text`` that the branch wrote: anything outside such a section, and the
    factory's own (park() writes 'Parked by the factory' first), are left out."""
    parts = re.split(r"^## ", text, flags=re.M)[1:]
    return "\n".join(p for p in parts if p.startswith("Where it stopped")
                     and not p.partition("\n")[2].lstrip().startswith("Parked by the factory"))


def size_gate(net: int, budget: int, first: str, wt: Path, rel: str) -> list[str]:
    """The size gate: an overrun blocks unless a reason for it (OVER_REASON) is written in the definition as first
    committed (``first``, which also gave the budget) or in a 'Where it stopped' section the branch's HEAD appended
    to it (appended(), stopped())."""
    if net <= budget or OVER_REASON.search(first) or OVER_REASON.search(stopped(appended(wt, rel, first))):
        return []
    return [f"size: {net} net lines of core code against a budget of {budget}, with no reason written (looked for in "
            f"{rel} as first committed and in a 'Where it stopped' section its HEAD appends to that, as a line that "
            "starts 'Overrun reason:')"]


def verdict(said: str) -> dict:
    blocks = VERDICT.findall(said)
    if not blocks:
        raise RuntimeError("the reviewer gave no fenced JSON verdict")
    v = json.loads(blocks[-1])
    if v.get("verdict") not in ("merge", "fix", "park"):
        raise RuntimeError(f"the reviewer's verdict is not merge, fix or park: {v.get('verdict')!r}")
    return {"verdict": v["verdict"], "blocking": [str(x) for x in v.get("blocking") or []],
            "non_blocking": [str(x) for x in v.get("non_blocking") or []],
            "where_it_stopped": str(v.get("where_it_stopped") or ""),
            **(parks.of_verdict(v) if v["verdict"] == "park" else {})}


def park(cfg: dict, gap: dict, why: str, by: str, where: str = "review", kind: str = "defect",
         until: dict | None = None) -> None:
    """Where it stopped, written into the definition file on the gap's branch (a commit this program makes in a clone
    of its own, pushed to the drop), then the gap parked: why as a kind (parks.KINDS) and, for the kinds a program
    resumes, what would end it (``until``). A park clears the last one's resume and need met (the same id parked
    again)."""
    branch = fac.branch_of(gap)
    d = agents.drop(cfg)
    if fac.git_ok(d, "rev-parse", "--verify", "-q", f"refs/heads/{fac.git_branch(branch)}"):
        _, work = agents.clone(cfg, branch, "park")
        rel = fac.definition_file(gap, work)
        if (work / rel).is_file():
            with (work / rel).open("a") as fh:
                fh.write(f"\n## Where it stopped\n\nParked by the factory ({by}, {time.strftime('%Y-%m-%d %H:%M')})."
                         f"\n\n{why.strip()}\n")
            fac.git(work, "-c", "user.name=factory", "-c", "user.email=factory@localhost", "commit", "-q", "-am",
                    f"{branch}: where it stopped\n\n{fac.TRAILER}")
            agents.publish(cfg, work, branch)
    fac.say("gap.parked", gap["id"], parked_at=time.time(), where_it_stopped=why[:4000], parked_by=by, parked_in=where,
            parked_for=kind, parked_until=until, resumed_as=None, resumed_at=None, need_met=None)


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
        return fac.guarded(given, began, "review_hours", lambda why: park(cfg, given["item"], why, "reviewer",
                                                                          kind="kill-rule"))


def next_review(branch: str) -> int:
    """The number of a new review of the branch: past the highest review/<branch>-N in the record, so a gap that
    continues a branch already reviewed (or its fix rounds) never reuses a parked gap's review item. A record that
    cannot be read raises (fac.items)."""
    got = [re.fullmatch(rf"review/{re.escape(branch)}-(\d+)", str(r.get("id"))) for r in fac.items("review")]
    return max([int(m[1]) for m in got if m] or [0]) + 1


def judge(cfg: dict, gap: dict, began: float) -> int:
    f = gap["fields"]
    if fac.drain_holds(cfg):
        return 0
    refused = fac.may_spend(cfg, float(cfg["ai"]["reviewer_session_usd"]))
    if refused:
        fac.nack(f"budget: {refused}", after="1h", count=False)
        return 0
    if not pools.my_turn(cfg, "reviewer", "reviewer", gap["id"]):
        fac.nack("the reviewer pool is full (run/pools.json): waits its turn", after="45s", count=False)   # (as implement.py)
        return 0
    branch, base = fac.branch_of(gap), f"origin/{cfg['git']['base']}"       # (in the clone made from the drop)
    n = int(f.get("reviews_n") or 0) + 1
    rid = f"review/{branch}-{next_review(branch)}"
    fac.say("gap.review-started", review_at=began, reviews_n=1)
    head = str(f.get("head") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise RuntimeError(f"{gap['id']} has no built head to review")
    home, wt = agents.clone(cfg, branch, "reviewer", at=head)
    rel = fac.definition_file(gap, wt)
    blocking, definition = gates(cfg, wt, branch, base, continued=bool(f.get("continues")),
                                 built_main=str(f.get("built_main") or ""), rel=rel)
    net, budget = fac.net_lines(wt, base, "HEAD"), fac.budget_of(definition)
    blocking += size_gate(net, budget, definition, wt, rel)
    diff = fac.git(wt, "diff", f"{base}...HEAD")
    if len(diff) > brief.DIFF_MOST:
        diff = (fac.git(wt, "diff", "--stat", f"{base}...HEAD") + "\n\n(the diff is too long to give whole: read it"
                f" with `git diff {base}...HEAD -- FILE`)")
    text, context = brief.assemble(
        cfg, "reviewer", gap, wt, definition=definition, diff=f"```diff\n{diff}\n```", net_lines=net, unlisted="\n".join(
            f"- `{p}`" for p in implement.unlisted(wt, base, "HEAD", definition)) or "(none)",
        gates="; ".join(blocking + [f"`ergostat check` finding allowed by the definition (judge its reason): {k}: {why}"
                                    for k, why in fac.allowances(definition).items()]) or "all passed")
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
                  review_hours=round((time.time() - began) / 3600, 3), resources=[got["resources"]] if got.get("resources") else [])
    failed = int(f.get("failed_gates") or 0) + (v["verdict"] == "fix")
    if v["verdict"] == "merge":
        fac.say("gap.approved", approved_at=time.time(), approved_by="review", first_pass=n == 1, reviewed_head=head,
                **record)
    elif v["verdict"] == "park" or failed >= fac.kill_after(cfg):
        why = v["where_it_stopped"] or f"Failed its gates {fac.kill_after(cfg)} times (the kill rule). Blocking findings:\n" + "\n".join(
            f"- {b}" for b in v["blocking"])
        fac.say("gap.measured", failed_gates=int(v["verdict"] == "fix"), findings=v["blocking"], **record)
        kind = (v["parked_for"], v["parked_until"]) if v["verdict"] == "park" else ("kill-rule", None)
        park(cfg, gap, why, rid, kind=kind[0], until=kind[1])
    else:
        fac.say("gap.sent-back", sent_back_by="review", findings=v["blocking"], failed_gates=1, fix_rounds=1,
                first_pass=False, **record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
