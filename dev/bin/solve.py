"""The backlog's solver (docs/roadmap/overnight/backlog.md): a proposed order of the gaps, deterministic.

A topological order by list scheduling: at each place, of the gaps whose dependencies in the backlog are placed, the
highest score. Score = WSJF (value / size points; risk multiplies the size) times (1 + BONUS for each backlog gap that
waits on it, however far: the critical path first). A pinned gap (`rank_pin: N`) takes place N once due, its unplaced
dependencies pulled ahead of it. Ties: the earlier rank, then the id. A cycle is refused, said as the finding."""

from __future__ import annotations

POINTS = {"S": 1.0, "M": 3.0, "L": 8.0}
RISK = {"low": 1.0, "medium": 1.25, "high": 1.5}
BONUS = 0.25
VALUE, SIZE = 3, "M"                     # assumed when a gap was never groomed


def points(size) -> float:
    """S/M/L, or estimated hours (four to a point)."""
    if isinstance(size, (int, float)) and not isinstance(size, bool) and size > 0:
        return max(0.25, float(size) / 4)
    return POINTS.get(str(size or "").upper(), POINTS[SIZE])


def cycle(graph: dict[str, set[str]]) -> list[str] | None:
    """A cycle along depends_on, as a path that ends where it starts, or None."""
    colour: dict[str, int] = {}
    for start in sorted(graph):
        if colour.get(start):
            continue
        colour[start], path, stack = 1, [start], [iter(sorted(graph[start]))]
        while stack:
            nxt = next(stack[-1], None)
            if nxt is None:
                colour[path.pop()] = 2
                stack.pop()
            elif colour.get(nxt) == 1:
                return path[path.index(nxt):] + [nxt]
            elif not colour.get(nxt) and nxt in graph:
                colour[nxt] = 1
                path.append(nxt)
                stack.append(iter(sorted(graph[nxt])))
    return None


def solve(gaps: dict[str, dict]) -> dict:
    """``gaps``: {id: {depends_on, value, size, risk, rank_pin, rank}} of the backlog (a dependency outside it is
    finished or underway: not waited on here). {order: [{id, rank, score, why}], findings: [...], refused: str|None}."""
    graph = {g: {d for d in (f.get("depends_on") or []) if d in gaps and d != g} for g, f in gaps.items()}
    loop = cycle(graph)
    if loop:
        return {"order": [], "findings": [f"refused: a cycle, {' -> '.join(loop)}"], "refused": " -> ".join(loop)}
    waiters: dict[str, set[str]] = {g: set() for g in gaps}
    for g, ds in graph.items():
        for d in ds:
            waiters[d].add(g)

    def under(g: str) -> set[str]:
        out, todo = set(), [g]
        while todo:
            for w in waiters[todo.pop()] - out:
                out.add(w)
                todo.append(w)
        return out

    def above(g: str) -> set[str]:
        out, todo = set(), [g]
        while todo:
            for d in graph[todo.pop()] - out:
                out.add(d)
                todo.append(d)
        return out

    score, why, findings = {}, {}, []
    for g, f in gaps.items():
        value = f.get("value") if isinstance(f.get("value"), (int, float)) else VALUE
        size = f.get("size") or SIZE
        risk = RISK.get(str(f.get("risk") or "").lower(), 1.0)
        n = len(under(g))
        wsjf = value / (points(size) * risk)
        score[g] = wsjf * (1 + BONUS * n)
        assumed = [x for x, k in (("value", "value"), ("size", "size")) if f.get(k) in (None, "")]
        why[g] = (f"WSJF {value:g}/{size}{f' x{risk:g} risk' if risk != 1 else ''} = {wsjf:.2f}"
                  + (f", x{1 + BONUS * n:g} for unblocking {n}" if n else "")
                  + (f" ({' and '.join(assumed)} assumed)" if assumed else ""))
    pins = {g: int(f["rank_pin"]) for g, f in gaps.items() if isinstance(f.get("rank_pin"), int)}
    prev = lambda g: gaps[g].get("rank") if isinstance(gaps[g].get("rank"), int) else 10**9  # noqa: E731
    best = lambda xs: min(xs, key=lambda g: (-round(score[g], 9), prev(g), g))  # noqa: E731
    placed: list[str] = []
    while len(placed) < len(gaps):
        place = len(placed) + 1
        ready = [g for g in gaps if g not in placed and graph[g] <= set(placed)]
        due = sorted((p, g) for g, p in pins.items() if g not in placed and p <= place)
        if due:
            pin, g = due[0]
            if g in ready:
                pick = g
            else:
                pick = best([a for a in ready if a in above(g)])
                why[pick] = f"{why[pick]}; pulled ahead of {g}, pinned at {pin}"
        else:
            pick = best([g for g in ready if g not in pins] or ready)
        if pick in pins:
            held = pins[pick] == place
            why[pick] = f"pinned at {pins[pick]}" + ("" if held else f", placed {place}: it waits on what comes first")
            if not held:
                findings.append(f"{pick}: pinned at {pins[pick]}, placed {place} (its dependencies come first)")
        placed.append(pick)
    return {"order": [{"id": g, "rank": n, "score": round(score[g], 3), "why": why[g]} for n, g in enumerate(placed, 1)],
            "findings": findings, "refused": None}
