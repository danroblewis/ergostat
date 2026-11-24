"""A checked graph (datasources/_frames.py) fitted to where it is drawn (SPEC §4e, *A graph*; the chart catalog's §2.2,
*Budgets* and *Aggregation stays honest*; G43, G45). Pure functions of the graph.

- **The panel's budget**: 40 nodes and 100 edges. Over it, nodes are collapsed by their declared ``group`` (a node whose
  id is a group's name joins it), then by their ``type``, then by weight into one ``other``, each step only while the
  last left too many; then the lightest edges are left out, and ``omitted`` says how many and what share of the weight.
- **Honest aggregation.** A node or an edge that holds others says how many (``holds``). Counts and rates (fields of
  role ``count``, ``rate`` or ``errors``, and an edge's ``n``) are summed; no other field is (latency, wait, age, slack,
  utilisation, exposure, or one with no role): it holds its worst member's value (the least slack, the most of the
  rest), and ``worst`` names that member. One unhealthy member marks its group. An edge inside a group is held by the
  group, not drawn. A route through a collapsed node is no evidence, so a collapsed graph's ``paths_real`` is false.
- **Analysis on the full graph.** ``acyclic`` is the full graph's, worked out before the fit, and kept.
- **The matrix** (chart 77): the same graph fitted to 300 rows (ND §12.3's budget, `[unsure]`: not measured here) and
  laid out as an adjacency matrix, its rows and columns ordered by group, then label; a cell is the weight of the
  edges from its row to its column."""

from __future__ import annotations

from collections import Counter

PANEL = (40, 100)
MATRIX = (300, 5000)
SUMMED = ("count", "rate", "errors")
LEAST_IS_WORST = ("slack",)
OTHER = "other"


def _weight(fields: list[dict], i: int) -> float:
    """What a node or edge weighs: its first summed field (else 1)."""
    for f in fields:
        if f.get("role") in SUMMED and f["values"][i] is not None:
            return float(f["values"][i])
    return 1.0


def _eweight(edges: dict, i: int) -> float | None:
    """What an edge weighs: its ``n``, else its first summed field, else 1; None when that is not known."""
    if "n" in edges:
        return None if edges["n"][i] is None else float(edges["n"][i])
    summed = [f for f in edges["fields"] if f.get("role") in SUMMED]
    return 1.0 if not summed else None if summed[0]["values"][i] is None else float(summed[0]["values"][i])


def _merged(fields: list[dict], members: list[list[int]], names: list[str]) -> tuple[list[dict], list[dict | None]]:
    """Each field over each set of ``members``: summed when it may be, else its worst member's (``worst``: whose).
    Null when any member's is: a partial sum is not the total, and the unknown member could be the worst."""
    out, worst = [], [None if len(m) == 1 else {} for m in members]
    for f in fields:
        values = []
        for k, m in enumerate(members):
            known = [(f["values"][i], i) for i in m if f["values"][i] is not None]
            if len(m) == 1 or len(known) < len(m):
                values.append(f["values"][m[0]] if len(m) == 1 else None)
            elif f.get("role") in SUMMED:
                values.append(sum(v for v, _ in known))
            else:
                v, i = (min if f.get("role") in LEAST_IS_WORST else max)(known)
                values.append(v)
                worst[k][f["name"]] = names[i]
        out.append({**f, "values": values})
    return out, worst


def _evidence(got: set[str]) -> str:
    if len(got) == 1:
        return next(iter(got))
    if got <= {"observed", "declared", "both"}:
        return "both"
    return "inferred" if "inferred" in got else "simulated"


def _keys(nodes: dict, most: int) -> tuple[list[str], list[str]]:
    """Each node's key once collapsed (its own id while it fits), and how it was collapsed."""
    ids, n = nodes["id"], len(nodes["id"])
    key, how = list(ids), []
    for col, word in (("group", "group"), ("type", "type")):
        if len(set(key)) <= most:
            break
        vals = nodes.get(col) or [None] * n
        names = set(v for v in vals if v is not None)
        of = [vals[i] if vals[i] is not None else ids[i] if col == "group" and ids[i] in names else None for i in range(n)]
        size = Counter(v for v in of if v is not None)
        new = [f"{word}:{of[i]}" if of[i] is not None and size[of[i]] > 1 and not key[i].startswith("group:") else key[i]
               for i in range(n)]
        if new != key:
            how.append(f"{len(set(key))} nodes collapsed by {word} into {len(set(new))}")
            key = new
    if len(set(key)) > most:
        weight: dict[str, float] = {}
        for i, k in enumerate(key):
            weight[k] = weight.get(k, 0.0) + _weight(nodes["fields"], i)
        kept = set(sorted(weight, key=lambda k: (-weight[k], k))[:most - 1])
        how.append(f"the lightest {len(weight) - len(kept)} into {OTHER!r}")
        key = [k if k in kept else OTHER for k in key]
    return key, how


def fit(g: dict, most_nodes: int, most_edges: int) -> tuple[dict, list[str]]:
    """``g`` within ``most_nodes`` and ``most_edges``, and how it was made to fit (nothing: it fitted as it was)."""
    nodes, edges = g["nodes"], g["edges"]
    key, how = _keys(nodes, most_nodes)
    order = list(dict.fromkeys(key))
    at = {k: j for j, k in enumerate(order)}
    members = [[] for _ in order]
    for i, k in enumerate(key):
        members[at[k]].append(i)
    one = lambda col, m: (lambda vs: vs[0] if len(set(vs)) == 1 else None)([col[i] for i in m])   # noqa: E731
    fields, worst = _merged(nodes["fields"], members, nodes["id"])
    new_nodes = {"id": order, "label": [nodes["label"][m[0]] if len(m) == 1 else k.split(":", 1)[-1]
                                        for k, m in zip(order, members, strict=True)],
                 "holds": [len(m) for m in members], "worst": worst, "fields": fields}
    for col in ("type", "group"):
        if col in nodes:
            new_nodes[col] = [one(nodes[col], m) for m in members]
    if "parent" in nodes:
        new_nodes["parent"] = [nodes["parent"][m[0]] if len(m) == 1 and nodes["parent"][m[0]] in at else None for m in members]
    if "health" in nodes:
        new_nodes["health"] = [("unhealthy" if "unhealthy" in hs else "ok" if hs == {"ok"} else None)
                               for hs in ({nodes["health"][i] for i in m} for m in members)]
    by: dict[tuple, list[int]] = {}
    inside = 0
    of = dict(zip(nodes["id"], key, strict=True))
    for i in range(len(edges["id"])):
        s, t = of[edges["source"][i]], of[edges["target"][i]]
        if s == t and edges["source"][i] != edges["target"][i]:
            inside += 1                                     # (held by its group)
            continue
        by.setdefault((s, t, edges["relation"][i]), []).append(i)
    ends, groups = list(by), list(by.values())
    weight = [None if any(w is None for w in ws) else sum(ws)
              for ws in ([_eweight(edges, i) for i in m] for m in groups)]
    known = None not in weight                            # an edge of unknown weight leaves the share unknown
    total = sum(w for w in weight if w is not None)
    if len(groups) > most_edges:
        keep = sorted(sorted(range(len(groups)), key=lambda j: -(weight[j] or 0.0))[:most_edges])
        cut = total - sum(weight[j] or 0.0 for j in keep)
        dropped, share = len(groups) - most_edges, (cut / total if known and total else None)
        how.append(f"the lightest {dropped} edges left out ({share:.0%} of the weight)" if share is not None
                   else f"{dropped} edges left out (their share of the weight is not known)")
        groups, ends = [groups[j] for j in keep], [ends[j] for j in keep]
    else:
        dropped, share = 0, 0.0
    efields, eworst = _merged(edges["fields"], groups, edges["id"])
    new_edges = {"id": [edges["id"][m[0]] if len(m) == 1 else f"{s}>{t}:{r}" for m, (s, t, r) in zip(groups, ends, strict=True)],
                 "source": [s for s, _, _ in ends], "target": [t for _, t, _ in ends], "relation": [r for _, _, r in ends],
                 "evidence": [_evidence({edges["evidence"][i] for i in m}) for m in groups],
                 "holds": [len(m) for m in groups], "worst": eworst, "fields": efields}
    for col, pick in (("n", sum), ("first_seen", min), ("last_seen", max), ("confidence", min)):
        if col in edges:                    # (an unknown n or confidence leaves the merged one unknown; a time not seen is not)
            new_edges[col] = [(lambda vs: pick(vs) if vs and (len(vs) == len(m) or col in ("first_seen", "last_seen")) else None)(
                [edges[col][i] for i in m if edges[col][i] is not None]) for m in groups]
    if inside:
        how.append(f"{inside} edges inside a collapsed node are held by it")
    if not how:
        return g, []
    om = g["omitted"]
    was = om.get("weight_share")
    joined = None if was is None or share is None else 1 - (1 - was) * (1 - share)   # an unknown stays unknown
    return {**g, "nodes": new_nodes, "edges": new_edges,
            "semantics": {**g["semantics"], "paths_real": g["semantics"]["paths_real"] and len(order) == len(key)},
            "omitted": {"nodes": om.get("nodes", 0), "edges": (om.get("edges") or 0) + dropped, "weight_share": joined,
                        "how": "; ".join(x for x in (om.get("how"), *how) if x)}}, how


def matrix(g: dict) -> dict:
    """``g`` as an adjacency matrix (chart 77): rows and columns the (fitted) nodes in group order, ``cells``
    ``[row, column, weight]``, and how it was fitted (``fitted``: empty when nothing was)."""
    shown, how = fit(g, *MATRIX)
    nodes, edges = shown["nodes"], shown["edges"]
    group = nodes.get("group") or [None] * len(nodes["id"])
    order = sorted(range(len(nodes["id"])), key=lambda i: (group[i] is None, group[i] or "", nodes["label"][i], nodes["id"][i]))
    row = {nodes["id"][i]: r for r, i in enumerate(order)}
    cells: dict[tuple[int, int], float | None] = {}
    for i in range(len(edges["id"])):
        w, at = _eweight(edges, i), (row[edges["source"][i]], row[edges["target"][i]])
        cells[at] = None if w is None or cells.get(at, 0.0) is None else cells.get(at, 0.0) + w   # unknown: null, never 1
    return {"ids": [nodes["id"][i] for i in order], "labels": [nodes["label"][i] for i in order],
            "group": [group[i] for i in order], "cells": [[r, c, w] for (r, c), w in sorted(cells.items())], "fitted": how}
