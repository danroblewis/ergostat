"""areas: the code areas the implementor is routed by (the implementor's `takes: {areas:}` in dev/model/building.yaml,
SPEC §9.5 *Areas*; dev/records/code-area-ownership.md), drawn from the conflict history and replayed against it.

    areas.py history [REPO] [REF]       each gap merged on REF (main): when its branch began and landed, the files it
                                        landed, the paths its definition named, and each merge of main into it that git
                                        stopped on (its message's `# Conflicts:` list): JSON
    areas.py draw [REPO] [REF]          the first map from that history, as the YAML of the block's `map:`
    areas.py replay [REPO] [REF]        the merges replayed with the model's map, as the dispatcher would hold them: the
                                        conflicted merges before and after, and the wait the rule adds (JSON)
    areas.py touches                    what the intake's pass does (intake.py): each gap in flight or waiting, the paths
                                        it touches (what its branch changed from main, and the paths its definition
                                        names) as `touches`, when they changed (gap.measured); [areas] route off: emptied

The history is git's own record: a conflicted merge's message keeps git's `# Conflicts:` list (each one a send-back
for a conflict, or a round's own merge of main that stopped on one). Nothing here reads or changes the live instance
but `touches`, which only says a field."""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

MERGE = re.compile(r"^Merge branch 'factory/([a-z0-9][a-z0-9-]{0,63})'")
NAMED = re.compile(r"\b((?:ergostat|dev|scripts|tests|docs|schema|examples)/[\w./*-]*\w)")
LEAST = 3            # conflicted merges naming a file before it is a hot area
LOAD = 2.0           # a lane carries at most this share of the history's hours in series (draw())
MOST = 40            # areas in the first map at most
TOUCHES = 2000       # paths written to a gap's field at most (the rule reads past 5000 as unreadable)
STATES = ("ready", "fix", "building", "built", "in-review", "approved", "queued", "push-pending", "queue-failed")


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args[:3])}: {r.stderr.strip()[-300:]}")
    return r.stdout


def conflicts_in(body: str) -> list[str]:
    """The files of a merge message's `# Conflicts:` list (git writes it when a merge stopped on them)."""
    _, sep, rest = body.partition("# Conflicts:\n")
    return sorted({ln[1:].strip() for ln in rest.splitlines() if ln.startswith("#\t")}) if sep else []


def named(text: str) -> list[str]:
    return sorted({m.rstrip(".") for m in NAMED.findall(text)})


def history(repo: Path, ref: str = "main") -> list[dict]:
    """Each gap merged on ``ref``'s first-parent line, oldest first. A merge git cannot read is an error, raised."""
    out = []
    for line in git(repo, "log", "--first-parent", "--merges", "--reverse", "--format=%H %P %ct %s", ref).splitlines():
        sha, p1, p2, at, subject = (line.split(" ", 4) + ["", "", "", "", ""])[:5]
        m = MERGE.match(subject)
        if not m or not at.isdigit():                    # (a merge of something else, or an octopus: not a gap's)
            continue
        own = git(repo, "log", "--format=%x1e%H%x1f%ct%x1f%B", f"{p1}..{p2}").split("\x1e")[1:]
        own = [c.split("\x1f", 2) for c in own]
        if not own:
            continue
        first = min(own, key=lambda c: int(c[1]))
        text = ""
        for p in (f"dev/records/{m.group(1)}.md", f"docs/roadmap/overnight/{m.group(1)}.md"):
            r = subprocess.run(["git", "-C", str(repo), "show", f"{first[0]}:{p}"], capture_output=True, text=True)
            if not r.returncode:
                text = r.stdout
                break
        out.append({"branch": m.group(1), "merge": sha, "began": int(first[1]), "landed_at": int(at),
                    "landed": sorted(filter(None, git(repo, "diff", "--name-only", p1, sha).splitlines())),
                    "named": named(text),
                    "conflicts": sorted(({"at": int(c[1]), "files": f} for c in own if (f := conflicts_in(c[2]))),
                                        key=lambda x: x["at"])})
    return out


def draw(gaps: list[dict], least: int = LEAST, load: float = LOAD, most: int = MOST) -> tuple[dict, dict]:
    """(the map: a lane for each file named in ``least`` conflicted merges or more, the most conflicted first, at most
    ``most``; the hot files left out, each with why). A file's **load** is the hours its gaps were in flight, summed,
    over the history's hours: what one lane would have to carry in series. Past ``load`` a lane cannot carry it
    without stretching the factory's work past its window (a file every gap touches is the limit of this), so it is
    left out, for an owner of another kind (a field's streams) or none."""
    hits: dict[str, int] = {}
    landed: dict[str, int] = {}
    hours: dict[str, float] = {}
    for g in gaps:
        for c in g["conflicts"]:
            for f in c["files"]:
                hits[f] = hits.get(f, 0) + 1
        for f in g["landed"]:
            landed[f] = landed.get(f, 0) + 1
            hours[f] = hours.get(f, 0.0) + (g["landed_at"] - g["began"]) / 3600
    window = (max(g["landed_at"] for g in gaps) - min(g["began"] for g in gaps)) / 3600 if gaps else 0.0
    hot = sorted((f for f, k in hits.items() if k >= least), key=lambda f: (-hits[f], f))
    out, left = {}, {}
    for f in hot:
        busy = round(hours.get(f, 0.0) / window, 2) if window > 0 else float("inf")
        row = {"conflicts": hits[f], "landed_by": landed.get(f, 0), "load": busy}
        if busy > load:
            left[f] = {**row, "why": f"load {busy} over {load}: a lane would carry it in series"}
        elif len(out) >= most:
            left[f] = {**row, "why": f"past the {most} areas of the map"}
        else:
            out[re.sub(r"[^a-z0-9]+", "-", f.lower()).strip("-")] = {"paths": [f], **row}
    return out, left


def areas_of(amap: dict, paths) -> set[str]:
    return {a for a, v in amap.items() if any(fnmatch.fnmatchcase(p, x) for x in v["paths"] for p in paths)}


def replay(gaps: list[dict], amap: dict, touches: str = "landed", wait: float | None = None) -> dict:
    """The merges replayed under the map's lanes (each gap its own stream: the record keeps no milestone in git), as
    the dispatcher holds them: a gap starts at its own start, or once no gap holding an area it touches is in flight
    (a gap holds from its start to its landing, each taking as long as it did). ``touches``: what the rule knows of
    a gap at its start: ``landed`` (the files it landed: what the rule could do at best) or ``named`` (the paths its
    definition named, and of the gaps already in, those and what they landed: what the live rule reads).

    A conflicted merge of main into a branch is explained when a gap landed one of its files while that branch was in
    flight; in the replay it stays when one still does. One no gap explains (a base, or a commit not a gap's) stays as
    it is. Added: each gap that, replayed, has a file that ever conflicted landed by another while it is in flight, and
    had no lander on that file before (a new collision, counted as a conflicted merge: an upper bound).
    No pool is modelled (the history's starts already carry the pools of their day)."""
    enter = {g["merge"]: areas_of(amap, g["landed"] if touches == "landed" else g["named"]) for g in gaps}
    holds = {g["merge"]: areas_of(amap, g["landed"] if touches == "landed" else [*g["named"], *g["landed"]])
             for g in gaps}
    done: list[dict] = []
    for g in sorted(gaps, key=lambda g: (g["began"], g["merge"])):
        span, t = g["landed_at"] - g["began"], g["began"]
        while True:
            clash = [h for h in done if h["start"] < t + span and t < h["end"]
                     and ((enter[g["merge"]] & holds[h["merge"]]) if h["start"] <= t
                          else (enter[h["merge"]] & holds[g["merge"]]))]
            if not clash:
                break
            t = max(h["end"] for h in clash)
            if wait is not None and t >= g["began"] + wait:
                t = g["began"] + wait                    # (waited its most: it goes, held or not)
                break
        done.append({"merge": g["merge"], "start": t, "end": t + span})
    was = {g["merge"]: (g["began"], g["landed_at"]) for g in gaps}
    now = {g["merge"]: (g["start"], g["end"]) for g in done}
    ever = {f for g in gaps for c in g["conflicts"] for f in c["files"]}
    files = {g["merge"]: set(g["landed"]) for g in gaps}

    def window(when: dict, g: dict) -> set[str]:
        """The gaps that landed while ``g`` was in flight."""
        s, e = when[g["merge"]]
        return {h for h, (_, end) in when.items() if h != g["merge"] and s < end < e}

    before = after = unexplained = added = 0
    for g in gaps:
        w_was, w_now = window(was, g), window(now, g)
        for c in g["conflicts"]:
            before += 1
            if not any(files[h] & set(c["files"]) for h in w_was):
                unexplained += 1
                after += 1
            elif any(files[h] & set(c["files"]) for h in w_now):
                after += 1
        hit_was = {f for h in w_was for f in files[h]}
        added += any(f not in hit_was for h in w_now for f in files[h] & files[g["merge"]] & ever)
    waits = [(now[b][0] - was[b][0]) / 3600 for b in was]
    span = (lambda w: (max(e for _, e in w.values()) - min(s for s, _ in w.values())) / 3600) if gaps else lambda w: 0
    return {"touches": touches, "wait": wait, "gaps": len(gaps), "areas": len(amap), "conflicted_before": before,
            "span_hours_before": round(span(was), 1), "span_hours_after": round(span(now), 1),
            "conflicted_after": after + added, "kept": after, "added": added, "unexplained": unexplained,
            "gaps_waited": sum(1 for w in waits if w > 0), "wait_hours_total": round(sum(waits), 1),
            "wait_hours_most": round(max(waits, default=0.0), 1)}


def model_map(path: Path) -> dict:
    """The implementor's `areas:` map as the model declares it (dev/model/building.yaml)."""
    import yaml
    blocks = yaml.safe_load(path.read_text())["blocks"]
    m = blocks["implementor"]["takes"]["areas"]["map"]
    return {k: {"paths": [v["paths"]] if isinstance(v["paths"], str) else v["paths"]} for k, v in m.items()}


def as_yaml(amap: dict) -> str:
    return "".join(f"        {k}: {{paths: [{', '.join(v['paths'])}]}}   # {v['conflicts']} conflicted merges, landed by "
                   f"{v['landed_by']}, load {v['load']}\n" for k, v in amap.items())


def routed(cfg: dict) -> bool:
    route = cfg.get("areas", {}).get("route", False)
    if not isinstance(route, bool):
        raise ValueError(f"[areas] route = {route!r}: true or false")
    return route


def measure(cfg: dict, g: dict, text: str | None = None) -> list | dict:
    """What a gap touches, as its `touches` field: with `[areas] route` on, the paths its definition names (``text``,
    or its definition read now) and the files its branch changed from main (the checkout's or the drop's
    factory/<branch>); off, [] (it touches no area). What cannot be read (the definition, the branch, the setting) is
    ``{"unread": why}``, which the rule reads as touching every area (lesson-3), never as touching none."""
    import brief
    import fac
    try:
        if not routed(cfg):
            return []
        branch = fac.branch_of(g)
        if text is None:
            text = brief.definition_text(cfg, str(g["fields"].get("definition") or ""), branch)
        if not text.strip():
            raise ValueError("its definition cannot be read")
        paths = set(named(text))
        for repo in (fac.path(cfg, "checkout"), fac.path(cfg, "live") / "drop.git"):
            ref = fac.git_branch(branch)
            if repo.exists() and fac.git_ok(repo, "rev-parse", "--verify", "-q", ref):
                paths |= set(filter(None, git(repo, "diff", "--name-only", f"{cfg['git']['base']}...{ref}").splitlines()))
                break
    except (ValueError, KeyError, RuntimeError, OSError, subprocess.SubprocessError) as e:
        why = f"{type(e).__name__}: {e}"[:300]
        print(f"{g['id']}: what it touches not read ({why}): every area", file=sys.stderr)
        return {"unread": why}
    return sorted(paths)[:TOUCHES]


def at_ready(gid: str, text: str | None, fields: dict) -> list | dict:
    """`touches` for the event that makes a gap ready (plan.route, parks.ready_again), so it is routed from its first
    look: what it touches, measured now, from the definition ``text`` it is made ready with (None: read now)."""
    import fac
    try:
        cfg = fac.config()
    except (OSError, ValueError, KeyError) as e:
        return {"unread": f"the factory's configuration ({type(e).__name__})"}
    return measure(cfg, {"id": gid, "state": "ready", "fields": fields}, text)


def touches(cfg: dict | None = None, gaps: list[dict] | None = None) -> int:
    """For each gap in a state the implementor takes or that holds an area, what it touches (measure()), said as
    `touches` when it differs from the field (the intake's pass calls it with what it read). With `[areas] route` off
    (or not set) that is [] (no gap touches any area), and any other gap's touches is emptied too; a route that is not
    true or false is a ValueError, and nothing is said. Returns how many gaps were said."""
    import fac
    cfg = cfg or fac.config()
    route = routed(cfg)
    n = 0
    for g in fac.items("gap") if gaps is None else gaps:
        if g["state"] not in STATES and (route or not g["fields"].get("touches")):
            continue
        got = measure(cfg, g)
        if got != g["fields"].get("touches"):
            fac.say("gap.measured", g["id"], touches=got)
            n += 1
    return n


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "touches"
    if cmd == "touches":
        print(f"areas: {touches()} gaps' touches said", file=sys.stderr)
        return 0
    repo = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[2]
    ref = argv[2] if len(argv) > 2 else "main"
    if cmd not in ("history", "draw", "replay"):
        print(__doc__, file=sys.stderr)
        return 2
    gaps = history(repo, ref)
    if cmd == "history":
        print(json.dumps(gaps, indent=1))
    elif cmd == "draw":
        amap, left = draw(gaps)
        print(as_yaml(amap), end="")
        print(json.dumps({"left_out_shared": left}, indent=1), file=sys.stderr)
    else:
        amap = model_map(repo / "dev" / "model" / "building.yaml")
        print(json.dumps([replay(gaps, amap, t) for t in ("landed", "named")], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
