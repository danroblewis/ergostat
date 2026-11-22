"""parks: why a gap was parked, as a kind, and what would end it; and the program that resumes a park once that clears
(docs/roadmap/overnight/park-owns-resume.md).

Each park records `parked_for`, one of KINDS, and for the kinds this program resumes `parked_until`, the condition:
{"gap": ID} or {"commits": [SHA, ...]} (waits_on: the gap's work, or its continuation's, or the commits, on main as
pushed: a merge not pushed has not cleared), {"action": WHAT, "who": WHO}
(needs: done once `gap.need-met` is recorded on the parked gap, with `need_met` saying what was done), {"gaps": [ID, ...]}
(split: every stopped sub-gap resumed or closed). defect and kill-rule are never resumed here: they are the pipeline
manager's (its park situations); deferred and cancelled are the coordinator's.

  parks.py resume   (every 5m, no AI) first each park from before kinds classified, once (classify()); then each
                    park whose condition cleared, resumed: a gap that continues its branch (as
                    by hand, manage.continue_gap); a split one back to split, its sub-gaps' continuations its children.
                    Each resume is `gap.resumed` on the parked gap with the condition that cleared."""

from __future__ import annotations

import fcntl
import re
import sys
import time

sys.dont_write_bytecode = True
import agents  # noqa: E402
import fac  # noqa: E402

KINDS = ("defect", "waits_on", "needs", "kill-rule", "deferred", "cancelled", "split", "unknown")  # unknown: classify()
RESUMED = ("waits_on", "needs", "split")                          # resumed by this program
WAITING = ("waits_on", "needs")                                  # past [manager] park_wait_hours: a situation
GAP = re.compile(r"(?:gap/)?([a-z0-9][a-z0-9-]{0,63})")
SHA = re.compile(r"[0-9a-f]{7,40}")
HOPS = 20                                    # a hard ceiling (lesson-4): continuations followed from a gap waited on
KILLERS = ("implementor", "plan-lint", "merge-queue", "dead-letters", "join-judge")   # parked_by of the kill rule's parks
COORDINATORS = ("plan-review", "pipeline-manager")                   # parked_by of the cancelled and deferred parks
CARRIED = re.compile(r"Merge branch '(?:factory/)?([a-z0-9][a-z0-9-]{0,63})'")


def of_verdict(v: dict) -> dict:
    """A reviewer's park verdict, as the fields of its park: its kind and condition. A kind the reviewer may not give,
    or waits_on / needs naming nothing that could clear, counts as the worst case, a defect (the pipeline manager
    looks at it), so no park waits on a condition no program can see."""
    kind, until = str(v.get("parked_for") or "defect"), None
    w = v.get("waits_on")
    names = [str(x).strip() for x in (w if isinstance(w, list) else [w]) if x]
    n = v.get("needs") if isinstance(v.get("needs"), dict) else {"action": v.get("needs")} if v.get("needs") else {}
    if kind == "waits_on" and len(names) == 1 and GAP.fullmatch(names[0]) and not SHA.fullmatch(names[0]):
        until = {"gap": f"gap/{GAP.fullmatch(names[0])[1]}"}
    elif kind == "waits_on" and names and all(SHA.fullmatch(x) for x in names):
        until = {"commits": names}
    elif kind == "needs" and str(n.get("action") or "").strip():
        until = {"action": str(n["action"]).strip()[:300], "who": str(n.get("who") or "coordinator").strip()[:100]}
    if kind not in ("waits_on", "needs") or until is None:
        return {"parked_for": "defect", "parked_until": None}
    return {"parked_for": kind, "parked_until": until}


def cleared(cfg: dict, g: dict, gaps: dict) -> str:
    """What cleared the park (said in its resume), or "" while it stands. A gap that is not in the record, a commit not
    found, a main not pushed, or a condition missing has not cleared."""
    f = g["fields"]
    kind, until = f.get("parked_for"), f.get("parked_until") if isinstance(f.get("parked_until"), dict) else {}
    if kind == "waits_on" and until.get("gap"):
        by = landed(cfg, str(until["gap"]), gaps)
        return f"{until['gap']} merged{f' as {by}' if by != until['gap'] else ''}, on {pushed(cfg)}" if by else ""
    if kind == "waits_on" and until.get("commits"):
        on = all(on_pushed(cfg, str(c)) for c in until["commits"])
        return f"{', '.join(str(c)[:12] for c in until['commits'])} on {pushed(cfg)}" if on else ""
    if kind == "needs" and until.get("action") and f.get("need_met"):
        return f"needed {until['action']} ({until.get('who')}): done, {str(f['need_met'])[:300]}"
    if kind == "split" and until.get("gaps"):
        ended = [gaps.get(c, {}).get("state") == "closed" or bool(gaps.get(c, {}).get("fields", {}).get("resumed_as"))
                 for c in until["gaps"]]
        return "its stopped sub-gaps resumed or closed: " + ", ".join(until["gaps"]) if all(ended) else ""
    return ""


def pushed(cfg: dict) -> str:
    return f"{cfg['git'].get('remote', 'origin')}/{cfg['git']['base']}"


def on_pushed(cfg: dict, sha: str) -> bool:
    """``sha`` is on main as pushed (the checkout's <remote>/<base>, which the queue's push and the upgrader's fetch
    move), never a local merge not pushed; a sha not a sha, or not found, is not."""
    return bool(SHA.fullmatch(sha)) and fac.git_ok(fac.path(cfg, "checkout"), "merge-base", "--is-ancestor", sha,
                                                   f"refs/remotes/{pushed(cfg)}")


def landed(cfg: dict, gid: str, gaps: dict) -> str:
    """The gap whose work is on pushed main: ``gid`` merged with its merge (main_sha) on it, or else its continuation
    (resumed_as, followed at most HOPS times; the original stays parked when it is continued); "" when none is."""
    for _ in range(HOPS):
        g = gaps.get(gid) or {"fields": {}}
        if g.get("state") == "merged" and on_pushed(cfg, str(g["fields"].get("main_sha") or "")):
            return gid
        if not (nxt := g["fields"].get("resumed_as")) or nxt == gid:   # (a split resumed is resumed as itself)
            return ""
        gid = str(nxt)
    return ""


def classify(cfg: dict) -> list[str]:
    """Each park from before kinds (no parked_for) given one once, under the continue lock (the resumer's and a
    continue's): the kill rule's by who parked it; one whose branch carries exactly one other gap's merge, waits_on that
    gap; any other, unknown (the pipeline manager's, raised by the watch whatever its age). A coordinator's park
    (deferred or cancelled, or parked by the plan review or the pipeline manager) is left alone, with nothing written,
    and so is one continued already (resumed_as: the original stays parked; its work goes on in the continuation)."""
    import manage
    done = []
    with open(fac.run_dir(cfg) / "continue.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        gaps = {g["id"]: g for g in fac.items("gap")}
        for g in gaps.values():
            f = g["fields"]
            if (g["state"] != "parked" or f.get("parked_for") or f.get("deferred") or f.get("cancelled")
                    or f.get("resumed_as") or f.get("parked_by") in COORDINATORS):
                continue
            by = str(f.get("parked_by") or "")
            kind, until = ("kill-rule", None) if by in KILLERS or by.startswith("queue run") else carried(cfg, g, gaps)
            manage.record("gap.measured", g["id"], parked_for=kind, parked_until=until, classified_by="park-classify",
                          classified_at=time.time())
            done.append(f"{g['id']} {kind}")
    return done


def carried(cfg: dict, g: dict, gaps: dict) -> tuple[str, dict | None]:
    """waits_on the one other gap whose branch g's branch merged in and main lacks (read from the merge's subject, in
    the drop); unknown for none, several, or a branch that cannot be read."""
    try:
        own = fac.branch_of(g)
        log = fac.git(agents.drop(cfg), "log", "--merges", "--format=%s",
                      f"{cfg['git']['base']}..refs/heads/{fac.git_branch(own)}", check=False)
    except ValueError:
        return "unknown", None
    names = {m[1] for s in log.splitlines() if (m := CARRIED.match(s))} - {own, cfg["git"]["base"]}
    roots = [x["id"] for x in gaps.values() if x["fields"].get("branch") in names and not x["fields"].get("continues")]
    return ("waits_on", {"gap": roots[0]}) if len(names) == 1 and len(roots) == 1 else ("unknown", None)


def resume(cfg: dict) -> list[str]:
    """Every park of a kind this program resumes whose condition cleared, resumed once (manage.continue_gap re-reads
    the park under the continue lock and refuses one resumed already, by hand or by a pass before)."""
    import manage
    manage.BY[0] = "park-resume"
    gaps, done = {g["id"]: g for g in fac.items("gap")}, []
    for g in gaps.values():
        f = g["fields"]
        if g["state"] != "parked" or f.get("parked_for") not in RESUMED or f.get("resumed_as"):
            continue
        why = cleared(cfg, g, gaps)
        if not why:
            continue
        try:
            done.append(split_again(g, gaps, why) if f["parked_for"] == "split" else
                        manage.continue_gap(cfg, g["id"], cleared=why, once=True)[0])
        except manage.Refused as e:                                 # (held by another gap: tried again next pass)
            print(f"parks: {g['id']} not resumed: {e}", file=sys.stderr)
    return done


def split_again(g: dict, gaps: dict, why: str) -> str:
    """A split gap whose stopped sub-gaps are each resumed or closed: back to split, joined once its children merge.
    Each stopped one is no longer its child (so split-watch does not park it again); a continuation is, instead."""
    import manage
    kin = lambda i: set(fac.ids(gaps.get(i, {}).get("fields", {}).get("parent")))  # noqa: E731
    for c in g["fields"]["parked_until"]["gaps"]:
        manage.record("gap.measured", c, parent={"set": sorted(kin(c) - {g["id"]})})
        if then := gaps.get(c, {}).get("fields", {}).get("resumed_as"):
            manage.record("gap.measured", then, parent={"set": sorted(kin(then) | {g["id"]})})
    manage.record("gap.split", g["id"], split_at=time.time())
    manage.record("gap.resumed", g["id"], resumed_as=g["id"], resumed_at=time.time(), resumed_for="split",
                  resumed_by=manage.BY[0], cleared=why)
    return g["id"]


def waiting(g: dict, now: float, hours: float) -> bool:
    """A waits_on or needs park not resumed, past its hours: the watch raises it, so nothing waits silently."""
    f = g["fields"]
    return (g["state"] == "parked" and f.get("parked_for") in WAITING and not f.get("resumed_as")
            and now - float(f.get("parked_at") or g.get("entered") or 0) > hours * 3600)


if __name__ == "__main__":
    if sys.argv[1:] != ["resume"]:
        sys.exit(__doc__)
    cfg = fac.config()
    fac.cli(cfg)
    print(f"parks: classified {', '.join(classify(cfg)) or 'nothing'}", file=sys.stderr)
    print(f"parks: resumed {', '.join(resume(cfg)) or 'nothing'}", file=sys.stderr)
