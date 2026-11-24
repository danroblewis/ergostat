"""The gaps' dependencies (the owner, 2026-11-20: "the gap items can have dependencies, so if there are any dependency
trees we can map those out"). Each gap's `depends_on` is an item relation (ergostat.yaml: precedence, SPEC 5a): a gap
is ready to build only once every gap it names is finished (`messages: done`: merged or closed); a parked gap is
paused (`messages: paused`), so it blocks what waits on it (ergostat's own status, and here `waits_on_parked` with
its `blocked_reason`, the implementor's `takes: where`); the implementor takes the unblocked first,
the critical first (`takes: unblocked`), the Process view and each gap's page draw the tree, and the completion
estimates wait on it.

Read, conservatively, from:
- the entries in main's dev/records/ as they render (gapsdoc.entries(); docs/GAPS.md only before the split): within an
  entry, `after `NAME``, `parked until `NAME``, `needs `NAME` first`, `depends on `NAME``, and a
  table whose header has a "Depends on" column beside a gap or branch column;
- a definition file: a line `depends-on: [name, ...]` (dev/records/<branch>.md; its shape: dev/prompts/definition.md);
- `gap.requested`: its `depends_on` (gap ids), already on the item.

A NAME is a gap's branch, its id's name, or a branch its GAPS entry names in backticks. Each link keeps where it came
from. A name that is no gap, a link that would close a cycle, or one on the gap's own ancestor (its `parent`, at any
depth: a split parent waits on its children) is never recorded: it is a dependency problem on the
gap (`dependency_problem`, the goal dependencies-sound), said, never dropped silently. A gap waiting on any unfinished
one says which and its state (`blocked_reason`; only a parked or dead one sets `waits_on_parked`); one whose branch is
already merged into main is said 'landed, not closed', for the coordinator to close; one in a starts_at state
(approved, queued, push-pending: fac.STACKABLE) is said 'stacked on X (approved)', as the gap is built on it.
A record that cannot be read (from_main()) is said by name on the gap it is the record of (its branch), and that gap
is held (`waits_on_parked`, its `blocked_reason` saying so): its dependencies are unknown, so it is never free.
`deps.py stacked` prints the count for the auxiliary gaps-stacked."""

from __future__ import annotations

import re
import sys

import fac

PHRASES = [re.compile(p, re.I) for p in (
    r"\bafter `([a-z0-9][a-z0-9-]*)`(?! (?:was|is|were) )",
    r"\bparked until `?([a-z0-9][a-z0-9-]*)`?",
    r"\bneeds `([a-z0-9][a-z0-9-]*)` first",
    r"\bdepends on `([a-z0-9][a-z0-9-]*)`",
)]
DONE = ("merged", "closed")                                        # finished (ergostat.yaml messages: done)
DEFLINE = re.compile(r"^depends-on:\s*\[([^\]]*)\]\s*$", re.M | re.I)
ENTRY = re.compile(r"^- \*\*(.+?)\*\*")


def from_gaps(text: str) -> tuple[dict[str, list[tuple[str, str]]], dict[str, set[str]]]:
    """({gap id: [(name, where it came from)]}, {gap id: the names its entry gives itself in backticks})."""
    deps: dict[str, list[tuple[str, str]]] = {}
    own: dict[str, set[str]] = {}
    gid, section, header = None, "", None
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            section, gid, header = line[3:].strip(), None, None
            continue
        if section.lower().startswith("done"):
            continue
        m = ENTRY.match(line)
        if m:
            gid = f"gap/{fac.slug(m.group(1).rstrip(':').strip(), 60)}"
            own[gid] = set(re.findall(r"(?:on|branch|from) `([a-z0-9][a-z0-9-]*)`", line))
        elif line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if any(c.lower() == "depends on" for c in cells):
                header = [c.lower() for c in cells]
                continue
            if header and len(cells) == len(header) and not set("".join(cells)) <= set("-: "):
                who = next((cells[i] for i, h in enumerate(header) if h in ("branch", "gap")), "")
                need = cells[header.index("depends on")]
                for name in re.findall(r"[a-z0-9][a-z0-9-]*", re.sub(r"\(.*?\)", "", need.replace("—", ""))):
                    deps.setdefault(f"@{who.strip('`')}", []).append((name, f"GAPS.md:{n} (the Depends on column)"))
            continue
        elif not line.startswith("  "):
            gid = None
        if gid:
            for rx in PHRASES:
                for name in rx.findall(line):
                    deps.setdefault(gid, []).append((name.lower(), f"GAPS.md:{n}: {line.strip()[:120]}"))
    return deps, own


def from_main(repo, ref: str, gaps_md: str) -> tuple[dict, dict[str, set[str]], dict[str, str]]:
    """from_gaps() of the entries in ``ref``'s dev/records/ (gapsdoc.entries()), and {record: why} for each that
    cannot be read; of ``gaps_md`` (``ref``'s docs/GAPS.md) only where ``ref`` has no GAPS-head.md (before the split)."""
    import gapsdoc  # (here: deps is loaded alone, by path, in tests)
    if (got := gapsdoc.entries(repo, ref)) is None:
        print(f"deps: {ref} has no {fac.DEFS}/GAPS-head.md: dependencies read from its docs/GAPS.md", file=sys.stderr)
    text, unreadable = got or (gaps_md, {})
    return (*from_gaps(text), unreadable)


def from_definition(text: str) -> list[str]:
    m = DEFLINE.search(text or "")
    return [x.strip().strip("`'\"") for x in m.group(1).split(",") if x.strip()] if m else []


def resolver(gaps: dict[str, dict], own: dict[str, set[str]]):
    """NAME (a gap id, a branch, an id's name, or a branch its entry names) -> the gap's id, or None."""
    names: dict[str, str] = {}
    for gid, g in gaps.items():
        for n in (gid, gid.split("/", 1)[1], g["fields"].get("branch") or "", *own.get(gid, ())):
            if n:
                names.setdefault(n.lower(), gid)
    return lambda name: names.get(name.lower()) or names.get(f"gap/{name.lower()}")


def reaches(graph: dict[str, set[str]], start: str, goal: str) -> list[str] | None:
    """A path from start to goal along depends_on, or None."""
    todo, seen = [[start]], {start}
    while todo:
        path = todo.pop()
        for nxt in graph.get(path[-1], ()):
            if nxt == goal:
                return path + [nxt]
            if nxt not in seen:
                seen.add(nxt)
                todo.append(path + [nxt])
    return None


ANCESTOR = "refused: depending on {} ({}), its own ancestor: a split parent waits on its children, so it would close a cycle"


def ancestors(gaps: dict[str, dict], gid: str) -> set[str]:
    """A gap's parent (``parent``, plan.py's split), its parent's, and so on, at any depth (a loop of parents ends)."""
    out: set[str] = set()
    todo = fac.ids(gaps[gid]["fields"].get("parent"))
    while todo:
        p = todo.pop()
        if p not in out and p != gid:
            out.add(p)
            todo += fac.ids((gaps.get(p) or {}).get("fields", {}).get("parent"))
    return out


def plan(gaps: dict[str, dict], parsed: dict[str, list[tuple[str, str]]], own: dict[str, set[str]],
         merged: set[str] = frozenset(), landed: set[str] = frozenset(),
         unreadable: dict[str, str] | None = None) -> dict[str, dict]:
    """Each gap's dependencies as they should be: {gap id: {depends_on, sources, problems, blocked_reason}}. Links are
    added one at a time; one that would close a cycle is refused and said. A name that is no gap but a branch already
    merged into main (``merged``) is work done: satisfied, kept as a source, no link; one the backlog took away
(``depends_on_removed``) is kept as a source, no link. A dependency is 'landed, not closed' only when its branch is in
    ``merged`` and its own work is on main: its definition (its branch's first commit) is in main's tree (``landed``,
    the stems of docs/roadmap/overnight/*.md there), so a branch made from main with no commits of its own is not.
    A gap whose record is in ``unreadable`` ({record: why}, from_main()) is held, said on it; each said on stderr."""
    find = resolver(gaps, own)
    graph = {gid: set(g["fields"].get("depends_on") or []) for gid, g in gaps.items()}
    out = {gid: {"sources": [], "problems": []} for gid in gaps}
    held = {}
    for name, why in sorted((unreadable or {}).items()):
        print(f"deps: {fac.DEFS}/{name}.md cannot be read ({why})", file=sys.stderr)
        if (gid := find(name)) in gaps:
            out[gid]["problems"].append(held.setdefault(gid, f"its record {fac.DEFS}/{name}.md cannot be read ({why}): "
                                                        "its dependencies are unknown, so held"))
    up = {gid: ancestors(gaps, gid) for gid in gaps}
    for gid in gaps:                                               # what the item already names (gap.requested)
        for d in list(graph[gid]):
            if d not in gaps or d in up[gid]:
                out[gid]["problems"].append(f"depends on {d}, which is no gap" if d not in gaps else ANCESTOR.format(d, "it"))
                graph[gid].discard(d)
    for key, links in parsed.items():
        gid = find(key[1:]) if key.startswith("@") else key
        if gid not in gaps:
            continue
        for name, where in links:
            dep = find(name)
            if dep is None and name in merged:
                out[gid]["sources"].append({"on": name, "from": where, "satisfied": "merged into main"})
            elif dep is None:
                out[gid]["problems"].append(f"depends on {name!r} ({where}), which is no gap")
            elif dep == gid:
                continue
            elif dep in up[gid]:
                out[gid]["problems"].append(ANCESTOR.format(dep, where))
            elif dep in (gaps[gid]["fields"].get("depends_on_removed") or []):    # taken away by the backlog
                out[gid]["sources"].append({"on": dep, "from": where, "removed": "by the backlog (backlog.py)"})
            elif dep in graph[gid]:
                out[gid]["sources"].append({"on": dep, "from": where})
            else:
                loop = reaches(graph, dep, gid)
                if loop:
                    out[gid]["problems"].append(f"refused: depending on {dep} ({where}) would close a cycle: "
                                                f"{' -> '.join([gid, *loop])}")
                else:
                    graph[gid].add(dep)
                    out[gid]["sources"].append({"on": dep, "from": where})
    for gid in gaps:
        out[gid]["depends_on"] = sorted(graph[gid])
        waits = [d for d in sorted(graph[gid]) if gaps[d]["state"] not in DONE]
        hold = [held[gid]] if gid in held and gaps[gid]["state"] not in DONE else []
        out[gid]["waits_on_parked"] = bool(hold) or any(gaps[d]["state"] in ("parked", "dead") for d in waits)
        out[gid]["blocked_reason"] = "" if gaps[gid]["state"] in DONE else "; ".join(
            hold + [waiting(d, gaps[d], merged, landed) for d in waits])
    return out


def waiting(d: str, g: dict, merged: set[str], landed: set[str] = frozenset()) -> str:
    """Why a gap waits on ``d``: its state, and 'landed, not closed' when its branch and its definition are on main."""
    try:
        b = fac.branch_of(g)
    except ValueError:
        b = ""
    if b and b in landed and {b, f"factory/{b}"} & set(merged):
        return f"waits on {d} ({g['state']}): landed, not closed (its branch {b} is on main; close it)"
    if g["state"] in ("parked", "dead"):
        return f"waits on {d}, which is {g['state']}: {stopped(g)}"
    if g["state"] in fac.STACKABLE:                    # (ergostat.yaml's starts_at: built on it, not waiting)
        return f"stacked on {d} ({g['state']})"
    return f"waits on {d}, which is {g['state']}"


def stopped(g: dict) -> str:
    why = str(g["fields"].get("where_it_stopped") or "").strip()
    return why.splitlines()[0][:160] if why else "stopped"


def changes(gaps: dict[str, dict], want: dict[str, dict]) -> list[tuple[str, dict]]:
    """The events to say: (gap id, data) for each gap whose dependencies, problems or blocked reason changed."""
    out = []
    for gid, w in want.items():
        f = gaps[gid]["fields"]
        data = {"depends_on": {"set": w["depends_on"]}, "depends_on_sources": w["sources"],
                "dependency_problems": w["problems"], "dependency_problem": bool(w["problems"]),
                "blocked_reason": w["blocked_reason"], "waits_on_parked": True if w.get("waits_on_parked") else None}
        same = (sorted(f.get("depends_on") or []) == w["depends_on"]
                and (f.get("dependency_problems") or []) == w["problems"]
                and (f.get("blocked_reason") or "") == w["blocked_reason"]
                and bool(f.get("waits_on_parked")) == bool(w.get("waits_on_parked"))
                and (f.get("depends_on_sources") or []) == w["sources"])
        if not same and (w["depends_on"] or w["problems"] or f.get("depends_on") or f.get("dependency_problems")
                         or w["blocked_reason"] or f.get("blocked_reason")):
            out.append((gid, data))
    return out


def node(gid: str, state: str) -> str:
    name = gid.split("/", 1)[1][:40]
    return f'{name}["{name} ({state})"]'


def tree(gaps: dict[str, dict]) -> str:
    """The dependency map as mermaid: each gap with a link, waiting on what it depends on."""
    lines = ["graph LR"]
    for gid, g in sorted(gaps.items()):
        for d in sorted(g["fields"].get("depends_on") or []):
            lines.append(f"  {node(d, gaps.get(d, {}).get('state', '?'))} --> {node(gid, g['state'])}")
    return "\n".join(lines) if len(lines) > 1 else "graph LR\n  %% no dependencies recorded"


def stacked(gaps: list[dict]) -> int:
    """The gaps built stacked on a base (a `stacked_on` that is not empty, or cannot be read) and not yet merged or
    closed: the auxiliary gaps-stacked (dev/model/building.yaml)."""
    return sum(g["state"] not in DONE and bool(g["fields"].get("stacked_on")) for g in gaps)


if __name__ == "__main__":
    import sys
    gaps = fac.items("gap")
    print(stacked(gaps) if sys.argv[1:] == ["stacked"] else tree({g["id"]: g for g in gaps}))
    sys.exit(0)
