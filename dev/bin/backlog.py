"""The backlog of gaps, groomed and ranked (docs/roadmap/overnight/backlog.md); run in the instance's folder.

    backlog.py show [-n N]                     the backlog in rank order: value, size, risk, what each waits on
    backlog.py pin GAP N | pin GAP --off       hold a gap at rank N (the solver and the groomer keep it)
    backlog.py dep add GAP ON | dep rm GAP ON  GAP waits on ON, or no longer (kept: the intake does not add it again)
    backlog.py close GAP (--done | --duplicate-of OTHER) --why TEXT
    backlog.py refuse-link GAP ON --why TEXT   a link GAP -> ON refused: never proposed again (dep add clears it)
    backlog.py propose [FILE]                  the solver's order and its reasons, or a proposal as checked; writes nothing
    backlog.py apply FILE                      a proposal (the gated action groom-backlog, once approved)
    backlog.py groom                           the groomer block: an AI session's proposal, solved, asked as groom-backlog

Each change re-ranks the backlog with the solver (solve.py) and says it as gap.groomed: rank, value, size, risk, why,
depends_on. A close is gap.closed (end done or duplicate); a duplicate's dependents wait on what it duplicates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import deps  # noqa: E402
import fac  # noqa: E402
import solve  # noqa: E402

BACKLOG = ("open", "replan", "planned", "ready", "fix")     # not started: what the ranks order
CLOSABLE = ("open", "replan", "planned", "ready")
FIELDS = ("value", "size", "risk", "groomed_why")   # (the coordinator's gap.dependencies wrote these names too)
JSON = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


say = fac.add                        # (by hand, or the approved action: about many gaps, so through ergostat)


def solved(gaps: dict[str, dict], over: dict[str, dict] | None = None) -> dict:
    """The solver over the backlog's gaps, each gap's fields with ``over`` on them."""
    rows = {gid: {**g["fields"], **(over or {}).get(gid, {})} for gid, g in gaps.items() if g["state"] in BACKLOG}
    return solve.solve(rows)


def rerank(gaps: dict[str, dict], by: str, over: dict | None = None, extra: dict | None = None) -> list[str]:
    """Write each gap whose rank (or ``extra`` fields) changed; the lines said. A refused order changes nothing."""
    got = solved(gaps, over)
    if got["refused"]:
        raise SystemExit(f"the solver refused: a cycle, {got['refused']} (backlog.py dep rm)")
    out = []
    for row in got["order"]:
        gid, more = row["id"], (extra or {}).get(row["id"], {})
        if gaps[gid]["fields"].get("rank") != row["rank"] or more:
            say("gap.groomed", gid, rank=row["rank"], rank_why=row["why"], ranked_by=by, ranked_at=time.time(), **more)
            out.append(f"  {row['rank']:>3}  {gid}  ({row['why']})")
    return out + [f"  note: {x}" for x in got["findings"]]


def refusals(cfg: dict) -> tuple[dict, list[str]]:
    """The links the coordinator refused (run/backlog/refused-links.jsonl, in file order: a later line wins, a `cleared`
    one ends it), and a note when it cannot be read: then it refuses nothing and says so (lesson-3)."""
    f, got = fac.run_dir(cfg, "backlog") / "refused-links.jsonl", {}
    try:
        for line in f.read_text().splitlines() if f.is_file() else []:
            r = json.loads(line)
            got[(r["gap"], r["depends_on"])] = None if r.get("cleared") else str(r.get("why") or "")
    except (OSError, ValueError, KeyError, TypeError) as e:
        return {}, [f"{f.name} could not be read, so it refuses no link ({str(e)[:200]})"]
    return {k: v for k, v in got.items() if v is not None}, []


def check(gaps: dict[str, dict], p: dict, known: tuple[dict, list[str]] = ({}, [])) -> tuple[dict, list[str]]:
    """A proposal as it can be applied, and what was refused: names that are no gap, links that close a cycle or are
    ``known`` (refusals()), fields of a pinned gap's rank, closes of gaps started, splits of a gap with built work."""
    refused, out = list(known[1]), {"links_add": [], "links_rm": [], "grooming": {}, "closes": [], "splits": []}
    graph = {gid: set(g["fields"].get("depends_on") or []) for gid, g in gaps.items()}
    for a, b, *why in p.get("links_rm") or []:
        if b in graph.get(a, ()):
            graph[a].discard(b)
            out["links_rm"].append([a, b, *why])
    for a, b, *why in p.get("links_add") or []:
        loop = deps.reaches(graph, b, a) if a in gaps and b in gaps and a != b else None
        if (a, b) in known[0]:
            refused.append(f"link {a} -> {b}: refused before by the coordinator ({known[0][(a, b)]})")
        elif a not in gaps or b not in gaps or a == b or loop:
            refused.append(f"link {a} -> {b}: " + (f"closes a cycle ({' -> '.join([a, *loop])})" if loop else "no gap"))
        elif b not in graph[a]:
            graph[a].add(b)
            out["links_add"].append([a, b, *why])
    for gid, f in (p.get("grooming") or {}).items():
        if gid in gaps:
            f = {**f, "groomed_why": f.get("groomed_why") or f.get("why")}
            out["grooming"][gid] = {k: f[k] for k in FIELDS if f.get(k) not in (None, "")}
    for c in p.get("closes") or []:
        g, of = gaps.get(c.get("gap")), c.get("of")
        if not g or g["state"] not in CLOSABLE or c.get("end") not in ("done", "duplicate") or (
                c["end"] == "duplicate" and (of not in gaps or of == c["gap"])):
            refused.append(f"close {c.get('gap')}: {g['state'] if g else 'no gap'}, or no end (done, duplicate of a gap)")
            continue
        moved = {d: (ds - {c["gap"]}) | ({of} if of and of != d else set())
                 for d, ds in graph.items() if c["gap"] in ds}           # its dependents wait on what it duplicates
        loop = next((x for d in moved if of and of != d and (x := deps.reaches({**graph, **moved}, of, d))), None)
        if loop:
            refused.append(f"close {c['gap']} as a duplicate of {of}: its dependents would close a cycle "
                           f"({' -> '.join(loop)})")
        else:
            graph.update(moved)
            out["closes"].append({**c, "repointed": sorted(moved)})
    for s in p.get("splits") or []:
        if s.get("gap") in gaps and gaps[s["gap"]]["state"] in CLOSABLE and 2 <= len(s.get("into") or []) <= 6 \
                and f"{s['gap']}-1" not in gaps:
            why = built(gaps[s["gap"]])
            if why:
                refused.append(f"split {s['gap']}: {why}; its parts would start from main and abandon that work")
            else:
                out["splits"].append(s)
    return out, refused


def built(g: dict) -> str | None:
    """Why the gap has built work a split would abandon: it continues a branch, or its branch in the drop has commits
    main lacks; a drop or branch that cannot be read counts as work (lesson-3). None: no branch, or none ahead."""
    if g["fields"].get("continues"):
        return f"it continues {g['fields']['continues']}"
    try:
        import agents
        cfg = fac.config()
        d, base = agents.drop(cfg), f"refs/heads/{cfg['git']['base']}"
        ref = f"refs/heads/{fac.git_branch(fac.branch_of(g))}"
        if not fac.git_ok(d, "rev-parse", "--verify", "-q", ref) and fac.git_ok(d, "rev-parse", "--verify", "-q", base):
            return None
        n = int(fac.git(d, "rev-list", "--count", f"{base}..{ref}"))
    except Exception as e:                                         # unreadable: the worst case, work
        return f"its branch could not be read ({str(e)[:200]})"
    return f"its branch has {n} commits main lacks" if n else None


def close(gaps: dict, gid: str, end: str, why: str, of: str | None, by: str) -> None:
    say("gap.closed", gid, end=end, closed_reason=why, closed_by=by, closed_at=time.time(),
        **({"duplicates": [of]} if of else {}))
    for d, g in gaps.items():
        if gid in (g["fields"].get("depends_on") or []):
            g["fields"]["depends_on"] = sorted({*g["fields"]["depends_on"], *([of] if of and of != d else [])} - {gid})
            say("gap.groomed", d, depends_on={"set": g["fields"]["depends_on"]}, groomed_by=by)
    gaps[gid]["state"] = "closed"


def apply(gaps: dict[str, dict], p: dict, by: str) -> tuple[list[str], list[str]]:
    """A checked proposal written, all or nothing: checked and solved whole first, then its links, closes, splits, and
    the grooming with the ranks; (lines, refused)."""
    p, refused = check(gaps, p, ({}, []) if by == "backlog.py" else refusals(fac.config()))
    if refused and by == "backlog.py":                # one change by hand: refused whole, nothing written
        raise SystemExit("\n".join(f"refused: {x}" for x in refused))
    order = solved(trial(gaps, p), p["grooming"])
    if order["refused"]:
        raise SystemExit(f"nothing written: the order would have a cycle, {order['refused']}")
    for a, b, *why in p["links_add"]:
        gaps[a]["fields"]["depends_on"] = sorted({*(gaps[a]["fields"].get("depends_on") or []), b})
        say("gap.groomed", a, depends_on={"add": [b]}, link_why=" ".join(why), groomed_by=by)
    for a, b, *why in p["links_rm"]:
        f = gaps[a]["fields"]
        f["depends_on"] = sorted(set(f.get("depends_on") or []) - {b})
        f["depends_on_removed"] = sorted({*(f.get("depends_on_removed") or []), b})
        say("gap.groomed", a, depends_on={"set": f["depends_on"]}, depends_on_removed=f["depends_on_removed"],
            link_why=" ".join(why), groomed_by=by)
    for c in p["closes"]:
        close(gaps, c["gap"], c["end"], str(c.get("reason") or ""), c.get("of"), by)
    for s in p["splits"]:
        kids, prev = [], []
        for part in s["into"]:
            kid = f"{s['gap']}-{len(kids) + 1}"
            say("gap.requested", kid, title=str(part.get("title") or kid)[:100], source="groom", parent=[s["gap"]],
                branch=fac.slug(s["gap"].split("/", 1)[1], 29) + f"-{len(kids) + 1}", depends_on=prev, why=str(part.get("why") or ""),
                requested_at=time.time())
            gaps[kid] = {"id": kid, "state": "open", "fields": {"depends_on": prev}}
            kids, prev = [*kids, kid], [kid]
        say("gap.split", s["gap"], children=kids, split_at=time.time(), split_by=by)
        gaps[s["gap"]]["state"] = "split"
    for gid, f in p["grooming"].items():
        f.update(groomed_by=by, groomed_at=time.time())
        gaps[gid]["fields"].update(f)
        if gaps[gid]["state"] not in BACKLOG:
            say("gap.groomed", gid, **f)
    lines = rerank(gaps, by, extra={k: v for k, v in p["grooming"].items() if gaps[k]["state"] in BACKLOG})
    return lines + [f"  refused: {x}" for x in refused], refused


def trial(gaps: dict[str, dict], p: dict) -> dict[str, dict]:
    """The gaps as a checked proposal would leave them (links, closes and their dependents re-pointed), on a copy."""
    t = json.loads(json.dumps(gaps))
    for a, b, *_ in p["links_add"]:
        t[a]["fields"]["depends_on"] = [*(t[a]["fields"].get("depends_on") or []), b]
    for a, b, *_ in p["links_rm"]:
        t[a]["fields"]["depends_on"] = [d for d in t[a]["fields"].get("depends_on") or [] if d != b]
    for c in p["closes"]:
        t[c["gap"]]["state"] = "closed"
        for d in c.get("repointed") or []:
            t[d]["fields"]["depends_on"] = sorted({*t[d]["fields"]["depends_on"], *([c["of"]] if c.get("of") and
                                                                                     c["of"] != d else [])} - {c["gap"]})
    return t


def diff(gaps: dict[str, dict], p: dict, refused: list[str]) -> str:
    """The proposal as the coordinator reads it: links, closes, splits, then each rank change, and the order."""
    order = solved(trial(gaps, p), p["grooming"])
    lines = [f"+ {a} waits on {b}: {''.join(w)}" for a, b, *w in p["links_add"]]
    lines += [f"- {a} no longer waits on {b}: {''.join(w)}" for a, b, *w in p["links_rm"]]
    lines += [f"x close {c['gap']} ({c['end']}{' of ' + c['of'] if c.get('of') else ''}): {c.get('reason', '')}"
              for c in p["closes"]]
    lines += [f"~ {d} waits on {c['of'] if c.get('of') and c['of'] != d else 'nothing'} instead of {c['gap']}"
              for c in p["closes"] for d in c.get("repointed") or []]
    lines += [f"/ split {s['gap']} into {len(s['into'])}: {'; '.join(str(x.get('title')) for x in s['into'])}"
              for s in p["splits"]]
    lines += [f"! refused: {x}" for x in refused + order["findings"]]
    for row in order["order"]:
        was = gaps[row["id"]]["fields"].get("rank")
        f = {**gaps[row["id"]]["fields"], **p["grooming"].get(row["id"], {})}
        lines.append(f"{row['rank']:>3} {'(was ' + str(was) + ')' if was != row['rank'] else '':<9} {row['id']}  "
                     f"v{f.get('value', '?')} {f.get('size', '?')} {f.get('risk', '?')}: {row['why']}")
    return "\n".join(lines)


def context(cfg: dict, gaps: dict[str, dict]) -> str:
    """What the groomer reads: each backlog gap whole, the module map, main's recent log."""
    import brief
    import knowledge
    rows = []
    for gid, g in sorted(gaps.items(), key=lambda x: (x[1]["fields"].get("rank") or 10**9, x[0])):
        if g["state"] not in BACKLOG:
            continue
        f = g["fields"]
        where = str(f.get("definition") or "")
        text = brief.definition_text(cfg, where, fac.branch_of(g))[:1500] if where else ""
        rows.append(f"### {gid} ({g['state']}{', pinned at ' + str(f['rank_pin']) if f.get('rank_pin') else ''})\n\n"
                    + json.dumps({k: f.get(k) for k in ("title", "branch", "continues", "source", "rank", "depends_on", *FIELDS)
                                  if f.get(k) not in (None, "", [])})
                    + f"\n\n{brief.gaps_entry(cfg, str(f.get('title') or ''))}\n\n{text}".rstrip())
    _, mods = knowledge.module_map(cfg)
    log = fac.git(fac.path(cfg, "checkout"), "log", "--oneline", "-150", cfg["git"]["base"], check=False)
    return ("# The backlog\n\n" + "\n\n".join(rows) + "\n\n# The module map\n\n"
            + knowledge.render_map(mods, [], 6000) + f"\n\n# Main's recent log\n\n```\n{log}\n```\n")


def groom(cfg: dict, gaps: dict[str, dict]) -> int:
    if fac.ai_held(cfg):
        print("groomer: the AI is held: next turn", file=sys.stderr)
        return 0
    d = fac.run_dir(cfg, "backlog")
    pending = d / "pending.json"
    if pending.is_file():
        aid = json.loads(pending.read_text()).get("action")
        r = fac.ergostat("item", aid, "--json", check=False) if aid else None
        if r is not None and r.returncode == 0 and json.loads(r.stdout).get("state") in ("requested", "approved", "held"):
            print(f"groomer: {aid} waits for the coordinator", file=sys.stderr)
            return 0
    open_ = {gid: g for gid, g in gaps.items() if g["state"] in BACKLOG}
    last = max([float(g["fields"].get("groomed_at") or 0) for g in open_.values()] or [0])
    new = [gid for gid, g in open_.items() if g["fields"].get("value") is None]     # never groomed
    if not open_ or not new and time.time() - last < float((cfg.get("backlog") or {}).get("every_hours", 12)) * 3600:
        print(f"groomer: nothing new in {len(open_)} gaps, groomed {(time.time() - last) / 3600:.1f}h ago",
              file=sys.stderr)
        return 0
    import agents
    _, work = agents.clone(cfg, "backlog", "groomer", at=f"origin/{cfg['git']['base']}")
    prompt = (fac.HERE / "prompts" / "groomer.md").read_text().replace("{context}", context(cfg, gaps))
    got = fac.attempt(cfg, "groomer", prompt, work)
    if got is None:
        return 0
    found = JSON.findall(str(got.get("result", "")))
    if not found:
        raise RuntimeError("the groomer gave no fenced JSON proposal")
    raw = json.loads(found[-1])
    p, refused = check(gaps, raw, refusals(cfg))
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    text = diff(gaps, p, refused)
    (d / f"{stamp}.md").write_text(f"# The backlog groomed, {stamp}\n\n```\n{text}\n```\n")
    (d / f"{stamp}.json").write_text(json.dumps(p, indent=1))
    summary = (f"{len(p['links_add'])} links added, {len(p['links_rm'])} removed, {len(p['closes'])} closes, "
               f"{len(p['splits'])} splits, {len(p['grooming'])} groomed: {fac.rel(d / f'{stamp}.md')}")
    rc, said = fac.act("groom-backlog", key=hashlib.sha1(json.dumps(p, sort_keys=True).encode()).hexdigest()[:12],
                       proposal=fac.rel(d / f"{stamp}.json"), summary=summary)
    aid = re.search(r"\((ergostat\.action/[0-9a-f]+)\)", said)
    pending.write_text(json.dumps({"action": aid[1] if aid else None, "proposal": f"{stamp}.json", "rc": rc}))
    print(f"groomer: asked groom-backlog ({rc}): {summary}", file=sys.stderr)
    return 0


def show(gaps: dict[str, dict], n: int) -> str:
    rows = sorted((g for g in gaps.values() if g["state"] in BACKLOG),
                  key=lambda g: (g["fields"].get("rank") or 10**9, g["id"]))
    out = [f"{'rank':>4}  {'gap':<44} {'state':<8} v  size risk    waits on"]
    for g in rows[:n]:
        f = g["fields"]
        waits = [d for d in f.get("depends_on") or [] if gaps.get(d, {}).get("state") not in ("merged", "closed")]
        out.append(f"{f.get('rank') or '-':>4}{'*' if f.get('rank_pin') else ' '} {g['id'][:44]:<44} {g['state']:<8} "
                   f"{f.get('value') or '?'}  {str(f.get('size') or '?'):<4} {str(f.get('risk') or '?'):<7} "
                   f"{', '.join(waits)}")
    return "\n".join(out + ([f"  ... and {len(rows) - n} more"] if len(rows) > n else []))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="backlog.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show").add_argument("-n", type=int, default=40)
    pin = sub.add_parser("pin")
    pin.add_argument("gap")
    pin.add_argument("rank", type=int, nargs="?")
    pin.add_argument("--off", action="store_true")
    dep = sub.add_parser("dep")
    dep.add_argument("how", choices=("add", "rm"))
    dep.add_argument("gap")
    dep.add_argument("on")
    cl = sub.add_parser("close")
    cl.add_argument("gap")
    cl.add_argument("--done", action="store_true")
    cl.add_argument("--duplicate-of")
    cl.add_argument("--why", required=True)
    ref = sub.add_parser("refuse-link")
    ref.add_argument("gap")
    ref.add_argument("on")
    ref.add_argument("--why", required=True)
    sub.add_parser("propose").add_argument("file", nargs="?")
    sub.add_parser("apply").add_argument("file")
    sub.add_parser("groom")
    a = ap.parse_args(argv)
    cfg = fac.config()
    fac.cli(cfg)
    gaps = {g["id"]: g for g in fac.items("gap")}
    name = lambda x: x if x.startswith("gap/") else f"gap/{x}"  # noqa: E731
    for attr in ("gap", "on", "duplicate_of"):
        if getattr(a, attr, None):
            setattr(a, attr, name(getattr(a, attr)))
            if getattr(a, attr) not in gaps:
                raise SystemExit(f"no such gap: {getattr(a, attr)}")
    by, refused = "backlog.py", []
    if a.cmd == "show":
        print(show(gaps, a.n))
        return 0
    if a.cmd == "groom":
        return groom(cfg, gaps)
    def remember(**f) -> None:                      # appended, one line each: a later line wins (refusals())
        with (fac.run_dir(cfg, "backlog") / "refused-links.jsonl").open("a") as w:
            w.write(json.dumps({"gap": a.gap, "depends_on": a.on, "at": time.time(), **f}) + "\n")
    if a.cmd == "refuse-link":
        remember(why=a.why)
        print(f"refused: {a.gap} -> {a.on} is not proposed again (backlog.py dep add clears it)")
        return 0
    if a.cmd == "propose" and a.file:
        p, refused = check(gaps, json.loads((fac.MODEL / a.file).read_text()), refusals(cfg))   # (an absolute path wins)
        print(diff(gaps, p, refused))
        return 0
    if a.cmd == "propose":
        got = solved(gaps)
        print("\n".join(f"{r['rank']:>3} (now {gaps[r['id']]['fields'].get('rank') or '-'}) {r['id']}: {r['why']}"
                        for r in got["order"]) or "nothing in the backlog")
        print("\n".join(got["findings"]))
        return 1 if got["refused"] else 0
    if a.cmd == "pin":
        if not a.off and (a.rank is None or a.rank < 1):
            raise SystemExit("pin GAP N (1 or more), or pin GAP --off")
        say("gap.groomed", a.gap, rank_pin=None if a.off else a.rank, pinned_by=by)
        gaps[a.gap]["fields"]["rank_pin"] = None if a.off else a.rank
        lines = rerank(gaps, by)
    elif a.cmd == "dep":
        lines, refused = apply(gaps, {f"links_{a.how}": [[a.gap, a.on, "by hand"]]}, by)
        if a.how == "add" and (a.gap, a.on) in refusals(cfg)[0]:     # an explicit decision overrides the refusal
            remember(cleared=True, why="dep add by hand")
    elif a.cmd == "close":
        if bool(a.done) == bool(a.duplicate_of):
            raise SystemExit("close GAP --done, or --duplicate-of OTHER")
        lines, refused = apply(gaps, {"closes": [{"gap": a.gap, "end": "done" if a.done else "duplicate",
                                                  "of": a.duplicate_of, "reason": a.why}]}, by)
    else:
        p = Path(a.file)
        lines, refused = apply(gaps, json.loads((p if p.is_absolute() else fac.MODEL / p).read_text()), "groomer")
        (fac.run_dir(cfg, "backlog") / "pending.json").unlink(missing_ok=True)
    print("\n".join(lines) or "no rank changed")
    return 2 if refused and a.cmd in ("dep", "close") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
