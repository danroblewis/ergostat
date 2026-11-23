"""intake: the factory's collector, the sensor of the whole workflow. Every few minutes it reads the gaps:

- each top-level entry of docs/GAPS.md on the checkout's main, outside *Done recently* and not itself done, that the
  record does not hold yet: `gap.found` (open); one GAPS.md marks done or superseded (`head`: the first clause of its
  opening parenthetical, or after its colon, begins with "done" or "superseded by") that the record holds not yet
  started: `gap.closed` (end done or duplicate); an entry listed twice (twice()) neither, but a dependency problem;
- requests submitted as events (`ergostat event --add gap.requested --item gap/NAME --data '{"title": ...}'`) are in
  the record already, open;
- each open gap with a definition of done: `gap.defined` (ready). A definition is the gap's `definition` field (a
  file in run/defs/), `run/defs/<branch>.md` in the instance's folder (written by the coordinator), or
  `dev/records/<branch>.md` (or, for a gap begun before the move, `docs/roadmap/overnight/<branch>.md`) on main or on
  the gap's branch; nothing else is read;
- a gap waiting for main to move (`waits_on_main`: its fast suites failed only on tests that fail on main too,
  onmain.py) released once the checkout's main is another commit (what the drop gives the implementor, and what the
  queue pushes to origin), so the implementor takes it again;
- a gap that `continues` an existing branch (`"continues": "NAME"`, e.g. a parked one): that branch fetched into the
  factory's drop as factory/<branch> first, so its own definition file is found there; one that cannot be fetched
  (the checkout lacks it, or the fetch fails) says so on the gap (`unfetched`), which the pipeline watch raises.

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

ENTRY = re.compile(r"^- \*\*(.+?)\*\*(.*)$")
BACKLOG = ("open", "replan", "planned", "ready")      # not started: a gap GAPS.md marks done is closed from these


def head(rest: str) -> str:
    """An entry's head (the text after its bold title, over its continuation lines, emphasis stripped): the first
    clause (up to the first `;`, `,` or `)`, lower case) of the parenthetical that opens it (balanced), or else of
    the text after its colon."""
    t = " ".join(rest.replace("*", "").split()).lstrip(":. ")
    paren = ""
    if t.startswith("("):
        depth = 0
        for n, c in enumerate(t):
            depth += {"(": 1, ")": -1}.get(c, 0)
            if depth == 0:
                paren = t[1:n]
                break
        else:
            paren = t[1:]
    return re.split(r"[;,)]", paren or t, maxsplit=1)[0].strip().lower()


def gaps_md(text: str) -> list[dict]:
    """Every entry of GAPS.md outside *Done recently*: title, section, its line, what it says of itself (gaps_says:
    done when its head's first clause begins with the word done, superseded when with "superseded by"; else parked,
    in progress or open, from that clause)."""
    out, section, cur = [], "", None
    for n, line in enumerate(text.splitlines(), 1):
        m = ENTRY.match(line)
        if cur is not None and not m and line.startswith("  "):
            cur["rest"] += " " + line
            continue
        cur = None
        if line.startswith("## "):
            section = line[3:].strip()
        elif m and not section.lower().startswith("done"):
            cur = {"title": m.group(1).rstrip(":").strip(), "section": section, "line": n, "rest": m.group(2)}
            out.append(cur)
    for e in out:
        first = head(e.pop("rest"))
        e["id"] = f"gap/{fac.slug(e['title'], 60)}"
        e["gaps_says"] = ("done" if re.match(r"done\b", first) else "superseded" if first.startswith("superseded by")
                          else "parked" if "parked" in first else
                          "in progress" if any(w in first for w in ("in progress", "landing", "awaiting")) else "open")
        e["head"] = first[:160]
    return out


def twice(text: str) -> dict[str, str]:
    """Each entry GAPS.md lists more than once, in any section (*Done recently* too), as a union merge
    (.gitattributes) can leave one: {gap id: the problem, naming every line}. Never resolved by picking one: such an
    entry is neither found nor closed, and is said (a dependency problem on its gap, or on stderr)."""
    at: dict[str, list[str]] = {}
    section = ""
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            section = line[3:].strip()
        elif m := ENTRY.match(line):
            at.setdefault(f"gap/{fac.slug(m.group(1).rstrip(':').strip(), 60)}", []).append(f"{n} ({section})")
    return {gid: f"GAPS.md lists it {len(w)} times, lines {', '.join(w)}: a merge left it twice; keep one by hand"
            for gid, w in at.items() if len(w) > 1}


def closed_by_gaps(known: dict[str, dict], entries: list[dict]) -> int:
    """A gap the record holds not yet started whose entry GAPS.md now marks done (or superseded): closed, saying so."""
    n = 0
    for e in entries:
        g = known.get(e["id"])
        if e["gaps_says"] in ("done", "superseded") and g and g["state"] in BACKLOG:
            fac.say("gap.closed", e["id"], end="done" if e["gaps_says"] == "done" else "duplicate",
                    closed_reason=f"GAPS.md:{e['line']} marks it {e['gaps_says']}: {e['head']}", closed_by="intake",
                    closed_at=time.time())
            g["state"] = "closed"
            n += 1
    return n


def definition(cfg: dict, gap: dict) -> str | None:
    """Where the gap's definition of done is (only run/defs/ or REF:dev/records/, brief.definition_text),
    or None; None too for a gap whose branch is not a safe name."""
    try:
        branch = fac.branch_of(gap)
    except ValueError as e:
        print(f"intake: {e}: not taken", file=sys.stderr)
        return None
    on = (cfg["git"]["base"], fac.git_branch(branch))
    refs = [f"{ref}:{d}/{branch}.md" for d in (fac.DEFS, fac.OLD_DEFS) for ref in on]     # the new path first
    for where in (str(gap["fields"].get("definition") or ""), f"run/defs/{branch}.md", *refs):
        text = brief.definition_text(cfg, where, branch) if where else ""
        if text.strip() and not fac.entry_only(text):                 # (a record holding only its GAPS.md entry)
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
        if gap["fields"].get("unfetched") != "fails the branch rule":     # (raised by the watch, as the others)
            fac.say("gap.measured", gap["id"], unfetched="fails the branch rule")
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
            if gap["fields"].get("unfetched"):            # held, not unfetched: an old cause is not raised on
                fac.say("gap.measured", gap["id"], unfetched=None)
            return False
    d, repo = agents.drop(cfg), fac.path(cfg, "checkout")
    if fac.git_ok(d, "rev-parse", "--verify", "-q", f"refs/heads/{ref}"):
        why = ""
    elif not fac.git_ok(repo, "rev-parse", "--verify", "-q", f"refs/heads/{name}"):
        why = "the checkout does not have"
    elif fac.git_ok(d, "fetch", "-q", str(repo), f"refs/heads/{name}:refs/heads/{ref}"):
        why = ""
    else:
        why = "could not be fetched into the drop"
    if why != (gap["fields"].get("unfetched") or ""):        # said once as it changes: the watch raises it (watch.py)
        fac.say("gap.measured", gap["id"], unfetched=why or None)
    if why:
        print(f"intake: {gap['id']} continues {name!r}, which {why}: not taken", file=sys.stderr)
    return not why


def dependencies(cfg: dict, known: dict[str, dict], text: str, dups: dict[str, str]) -> int:
    """Each gap's dependencies from GAPS.md, its definition's `depends-on:` line and what was asked, and an entry
    GAPS.md lists twice (``dups``, twice()) as a problem: said as gap.dependencies where they changed (deps.py)."""
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
    tree = fac.git(repo, "ls-tree", "--name-only", cfg["git"]["base"], "docs/roadmap/overnight/", check=False)
    landed = {f.rsplit("/", 1)[-1][:-3] for f in tree.split() if f.endswith(".md")}   # unread: none, never 'landed'
    want = deps.plan(known, parsed, own, merged, landed)
    for gid, why in dups.items():
        if gid in want:
            want[gid]["problems"].append(why)
        else:
            print(f"intake: {gid}: {why}", file=sys.stderr)
    for gid, data in deps.changes(known, want):
        fac.say("gap.dependencies", gid, **data)
        n += 1
    return n


def main_moved(cfg: dict, known: dict[str, dict]) -> int:
    """Each gap waiting on a main commit that is no longer the checkout's main, released (`waits_on_main` cleared)."""
    now = fac.git(fac.path(cfg, "checkout"), "rev-parse", cfg["git"]["base"])
    moved = [g for g in known.values() if g["fields"].get("waits_on_main") not in (None, "", now)]
    for g in moved:
        fac.say("gap.measured", g["id"], waits_on_main=None, main_moved_to=now)
    return len(moved)


def main() -> int:
    cfg = fac.config()
    repo = fac.path(cfg, "checkout")
    known = {g["id"]: g for g in fac.items("gap")}
    now = time.time()
    found = 0
    text = fac.git(repo, "show", f"{cfg['git']['base']}:docs/GAPS.md")
    dups = twice(text)
    entries = [e for e in gaps_md(text) if e["id"] not in dups]
    closed = closed_by_gaps(known, entries)
    for e in entries:
        if e["id"] not in known and e["gaps_says"] not in ("done", "superseded"):
            gid = e.pop("id")
            del e["line"], e["head"]
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
        elif g["fields"].get("continues"):                     # the planner never takes it: said, never waiting silently
            print(f"intake: {g['id']} continues a branch with no definition of done on it: not taken", file=sys.stderr)
    linked = dependencies(cfg, known, text, dups)
    released = main_moved(cfg, known)
    print(f"intake: {found} found, {closed} closed (GAPS.md marks them done), {defined} defined, {linked} with their "
          f"dependencies changed, {released} released by main moving", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
