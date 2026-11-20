"""intake: the factory's collector, the sensor of the whole workflow. Every few minutes it reads the gaps:

- each top-level entry of docs/GAPS.md on the checkout's main, outside *Done recently* and not itself done, that the
  record does not hold yet: `gap.found` (open);
- requests submitted as events (`ergostat event --add gap.requested --item gap/NAME --data '{"title": ...}'`) are in
  the record already, open;
- each open gap with a definition of done: `gap.defined` (ready). A definition is the gap's `definition` field (a
  file in run/defs/), `run/defs/<branch>.md` in the instance's folder (written by the coordinator), or
  `docs/roadmap/overnight/<branch>.md` on main or on the gap's branch; nothing else is read;
- a gap that `continues` an existing branch (`"continues": "NAME"`, e.g. a parked one): that branch fetched into the
  factory's drop as factory/<branch> first, so its own definition file is found there.

It reads the checkout with commands that write nothing; the drop is the only repository it writes to (that fetch). Run
as a block: its lines are the record's."""

from __future__ import annotations

import re
import sys
import time

sys.dont_write_bytecode = True
import agents  # noqa: E402
import brief  # noqa: E402
import deps  # noqa: E402
import fac  # noqa: E402

ENTRY = re.compile(r"^- \*\*(.+?)\*\*\s*(\((?:[^()]|\([^()]*\))*\))?")


def gaps_md(text: str) -> list[dict]:
    """The entries of GAPS.md still to do: title, section, what it says of itself, the branches it names."""
    out, section = [], ""
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        m = ENTRY.match(line)
        if not m or section.lower().startswith("done"):
            continue
        paren = (m.group(2) or "").lower()
        if paren.startswith("(done"):
            continue
        title = m.group(1).rstrip(":").strip()
        out.append({"id": f"gap/{fac.slug(title, 60)}", "title": title, "section": section,
                    "gaps_says": "parked" if ("parked" in paren or "stopped" in paren) else
                    "in progress" if "in progress" in paren else "open"})
    return out


def definition(cfg: dict, gap: dict) -> str | None:
    """Where the gap's definition of done is (only run/defs/ or REF:docs/roadmap/overnight/, brief.definition_text),
    or None; None too for a gap whose branch is not a safe name."""
    try:
        branch = fac.branch_of(gap)
    except ValueError as e:
        print(f"intake: {e}: not taken", file=sys.stderr)
        return None
    rel = f"{fac.DEFS}/{branch}.md"
    for where in (str(gap["fields"].get("definition") or ""), f"run/defs/{branch}.md", f"{cfg['git']['base']}:{rel}",
                  f"{fac.git_branch(branch)}:{rel}"):
        if where and brief.definition_text(cfg, where, branch).strip():
            return where
    return None


def continued(cfg: dict, gap: dict, known: dict[str, dict]) -> bool:
    """A gap that `continues` a branch of the checkout: that branch fetched into the drop as its factory/<branch> when
    the drop has none (a fetch that never forces: work already there is kept). False (not taken, said) for a name that
    fails the branch rule, a branch the checkout does not have, or a branch another known gap still holds (any state but
    parked or merged: its work and reviews are its own until it stops; another open request to continue it holds
    nothing yet, and the first taken holds it from then on); True for every other gap."""
    name = str(gap["fields"].get("continues") or "")
    if not name:
        return True
    try:
        branch = fac.branch_of(gap)
        ref = fac.git_branch(branch)
    except ValueError as e:
        print(f"intake: {e}: not taken", file=sys.stderr)
        return False
    for other in known.values():
        try:
            same = other["id"] != gap["id"] and fac.branch_of(other) == branch
        except ValueError:
            continue
        waiting = other["state"] == "open" and other["fields"].get("continues")
        if same and not waiting and other["state"] not in ("parked", "merged"):
            print(f"intake: {gap['id']} continues {name!r}, which {other['id']} still holds ({other['state']}): "
                  "not taken until it is parked or merged", file=sys.stderr)
            return False
    d = agents.drop(cfg)
    if fac.git_ok(d, "rev-parse", "--verify", "-q", f"refs/heads/{ref}"):
        return True
    repo = fac.path(cfg, "checkout")
    if not fac.git_ok(repo, "rev-parse", "--verify", "-q", f"refs/heads/{name}"):
        print(f"intake: {gap['id']} continues {name!r}, which the checkout does not have: not taken", file=sys.stderr)
        return False
    return fac.git_ok(d, "fetch", "-q", str(repo), f"refs/heads/{name}:refs/heads/{ref}")


def dependencies(cfg: dict, known: dict[str, dict], text: str) -> int:
    """Each gap's dependencies from GAPS.md, its definition's `depends-on:` line and what was asked: said as
    gap.dependencies where they changed (deps.py)."""
    parsed, own = deps.from_gaps(text)
    for gid, g in known.items():
        where = str(g["fields"].get("definition") or "")
        if where:
            try:
                names = deps.from_definition(brief.definition_text(cfg, where, fac.branch_of(g)))
            except ValueError:
                names = []
            parsed.setdefault(gid, []).extend((n, f"its definition ({where})") for n in names)
    n = 0
    repo = fac.path(cfg, "checkout")
    merged = set(fac.git(repo, "branch", "--format=%(refname:short)", "--merged", cfg["git"]["base"],
                         check=False).split())
    for gid, data in deps.changes(known, deps.plan(known, parsed, own, merged)):
        fac.say("gap.dependencies", gid, **data)
        n += 1
    return n


def main() -> int:
    cfg = fac.config()
    repo = fac.path(cfg, "checkout")
    known = {g["id"]: g for g in fac.items("gap")}
    now = time.time()
    found = 0
    text = fac.git(repo, "show", f"{cfg['git']['base']}:docs/GAPS.md")
    for e in gaps_md(text):
        if e["id"] not in known:
            gid = e.pop("id")
            fac.say("gap.found", gid, **e, source="gaps", branch=fac.slug(gid.split("/", 1)[1], 32), open_at=now)
            known[gid] = {"id": gid, "state": "open", "fields": {**e, "branch": fac.slug(gid.split("/", 1)[1], 32)}}
            found += 1
    defined = 0
    for g in known.values():
        if g["state"] != "open" or not continued(cfg, g, known):
            continue
        where = definition(cfg, g)
        if where:
            fac.say("gap.defined", g["id"], definition=where, ready_at=now, branch=fac.branch_of(g),
                    defined_by="coordinator")
            g["fields"]["definition"], g["state"] = where, "ready"
            defined += 1
    linked = dependencies(cfg, known, text)
    print(f"intake: {found} found, {defined} defined, {linked} with their dependencies changed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
