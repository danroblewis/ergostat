"""The gaps' dependencies (the owner, 2026-11-20: "the gap items can have dependencies, so if there are any dependency
trees we can map those out"). Each gap's `depends_on` is an item relation (ergostat.yaml: precedence, SPEC 5a): a gap
is ready to build only once every gap it names is finished (`messages: done`: merged, or parked, so the estimates
never carry a parked gap as open), and never while one is parked (`waits_on_parked`, the implementor's
`takes: where`); the implementor takes the unblocked first,
the critical first (`takes: unblocked`), the Process view and each gap's page draw the tree, and the completion
estimates wait on it.

Read, conservatively, from:
- docs/GAPS.md: within an entry, `after `NAME``, `parked until `NAME``, `needs `NAME` first`, `depends on `NAME``, and a
  table whose header has a "Depends on" column beside a gap or branch column;
- a definition file: a line `depends-on: [name, ...]` (docs/roadmap/overnight/TEMPLATE.md);
- `gap.requested`: its `depends_on` (gap ids), already on the item.

A NAME is a gap's branch, its id's name, or a branch its GAPS entry names in backticks. Each link keeps where it came
from. A name that is no gap, or a link that would close a cycle, is never recorded: it is a dependency problem on the
gap (`dependency_problem`, the goal dependencies-sound), said, never dropped silently. A gap waiting on a parked one
says so (`blocked_reason`)."""

from __future__ import annotations

import re

import fac

PHRASES = [re.compile(p, re.I) for p in (
    r"\bafter `([a-z0-9][a-z0-9-]*)`(?! (?:was|is|were) )",
    r"\bparked until `?([a-z0-9][a-z0-9-]*)`?",
    r"\bneeds `([a-z0-9][a-z0-9-]*)` first",
    r"\bdepends on `([a-z0-9][a-z0-9-]*)`",
)]
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


def plan(gaps: dict[str, dict], parsed: dict[str, list[tuple[str, str]]], own: dict[str, set[str]],
         merged: set[str] = frozenset()) -> dict[str, dict]:
    """Each gap's dependencies as they should be: {gap id: {depends_on, sources, problems, blocked_reason}}. Links are
    added one at a time; one that would close a cycle is refused and said. A name that is no gap but a branch already
    merged into main (``merged``) is work done: satisfied, kept as a source, no link."""
    find = resolver(gaps, own)
    graph = {gid: set(g["fields"].get("depends_on") or []) for gid, g in gaps.items()}
    out = {gid: {"sources": [], "problems": []} for gid in gaps}
    for gid in gaps:                                               # what the item already names (gap.requested)
        for d in list(graph[gid]):
            if d not in gaps:
                out[gid]["problems"].append(f"depends on {d}, which is no gap")
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
        parked = [d for d in graph[gid] if gaps[d]["state"] in ("parked", "dead")]
        out[gid]["blocked_reason"] = "; ".join(f"waits on {d}, which is {gaps[d]['state']}: {stopped(gaps[d])}"
                                               for d in sorted(parked))
    return out


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
                "blocked_reason": w["blocked_reason"], "waits_on_parked": True if w["blocked_reason"] else None}
        same = (sorted(f.get("depends_on") or []) == w["depends_on"]
                and (f.get("dependency_problems") or []) == w["problems"]
                and (f.get("blocked_reason") or "") == w["blocked_reason"]
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


if __name__ == "__main__":
    import sys
    print(tree({g["id"]: g for g in fac.items("gap")}))
    sys.exit(0)
