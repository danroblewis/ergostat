"""The layout rules of docs/layout-rules.md, each a detector over a diagram's drawn geometry (what
scripts/layout_geometry.js reads off the page: parts' boxes and their labels, lines' points, the words as drawn,
loop markers, open systems' frames). Each detector returns the instances it finds, each with a severity and a
score (how bad: in pixels, or a count), the parts it is about and the box round it (for a crop of a screenshot).

Pure Python, no browser: tests/test_diagram_rendering.py runs the fast ones on every view it draws, and
scripts/layout_corpus.py runs all of them over a corpus of models. The rules are in the order of the document:
the worst-looking first."""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

# ------------------------------------------------------------------ the thresholds (docs/layout-rules.md)

GRID = 56                 # one step of the layout: ELK's space between layers (layouts.js TIGHT)
CLOUD_GAP = 70            # a cloud lies at most this far from its valve (box to box): a step and a little
CLOUD_FAR = 220           # past this, the cloud reads as belonging to something else
EXCURSION_K = 1.3         # a flow's way from end to end at most this many times the direct (Manhattan) distance,
EXCURSION_SLACK = 80      # plus this (the valve's width and a jog)
VALVE_BOX_SLACK = 30      # a valve inside the box its two ends span, grown by this (half a valve and a margin)
CLOUD_FLOW_BENDS = 0      # a flow to or from a cloud: straight
STOCK_FLOW_BENDS = 2      # a flow between two stocks: at most a jog (a flow back up a chain may need 4)
BACK_FLOW_BENDS = 4
LINE_BENDS = 6            # any other line
CONNECTOR_DETOUR_K, CONNECTOR_DETOUR_SLACK = 2.0, 160
SATELLITE_GAP = 160       # a goal's desired level by its gap, a gap by the valve it drives
STRANDED_GAP = 420        # a part with nothing it is joined to nearer than this
OVERLAP_MIN = 20          # two lines on one track for longer than this
MIN_FIT, MAX_ASPECT = 0.7, 4.0


@dataclass(frozen=True)
class Rule:
    name: str
    severity: str         # critical | major | minor: how bad it looks
    views: tuple          # the views it applies to ("dynamics", "blocks", "process")
    fast: bool            # cheap enough for every view in the normal suite
    detect: Callable
    says: str


# ------------------------------------------------------------------ geometry

def rect(n) -> tuple:
    return (n["x"], n["y"], n["x"] + n["w"], n["y"] + n["h"])


def box4(b) -> tuple:
    return (b[0], b[1], b[0] + b[2], b[1] + b[3])


def centre(r) -> tuple:
    return ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)


def shrink(r, m) -> tuple:
    return (r[0] + m, r[1] + m, r[2] - m, r[3] - m)


def gap(a, b) -> float:
    """The distance between two boxes (0 when they meet)."""
    dx = max(0.0, a[0] - b[2], b[0] - a[2])
    dy = max(0.0, a[1] - b[3], b[1] - a[3])
    return math.hypot(dx, dy)


def inter(a, b) -> float:
    """The area two boxes share."""
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def union(*rs) -> tuple:
    return (min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs))


def seg_box(a, b) -> tuple:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))


def segs(pts):
    return list(zip(pts, pts[1:], strict=False))


def length(pts) -> float:
    return sum(math.dist(a, b) for a, b in segs(pts))


def clip(a, b, r) -> float:
    """How much of the segment a-b lies inside the box r (Liang-Barsky)."""
    x0, y0 = a
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - r[0]), (dx, r[2] - x0), (-dy, y0 - r[1]), (dy, r[3] - y0)):
        if abs(p) < 1e-9:
            if q < 0:
                return 0.0
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return 0.0
    return (t1 - t0) * math.hypot(dx, dy)


def bends(pts) -> int:
    """Corners: where a line changes direction (by more than a few degrees)."""
    n = 0
    clean = [p for i, p in enumerate(pts) if i == 0 or math.dist(p, pts[i - 1]) > 0.5]
    for a, b, c in zip(clean, clean[1:], clean[2:], strict=False):
        u, v = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
        cr = abs(u[0] * v[1] - u[1] * v[0]) / (math.hypot(*u) * math.hypot(*v) + 1e-9)
        dot = u[0] * v[0] + u[1] * v[1]
        if cr > 0.08 or dot < 0:
            n += 1
    return n


def manhattan(a, b) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def collinear_overlap(a, b, c, d, tol=3.0) -> float:
    """How far two axis-parallel stretches run on one track."""
    if abs(a[1] - b[1]) < 1 and abs(c[1] - d[1]) < 1 and abs(a[1] - c[1]) < tol:
        return min(max(a[0], b[0]), max(c[0], d[0])) - max(min(a[0], b[0]), min(c[0], d[0]))
    if abs(a[0] - b[0]) < 1 and abs(c[0] - d[0]) < 1 and abs(a[0] - c[0]) < tol:
        return min(max(a[1], b[1]), max(c[1], d[1])) - max(min(a[1], b[1]), min(c[1], d[1]))
    return 0.0


def crosses(a, b, c, d) -> bool:
    """Whether two segments cross properly (not at an end)."""
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return o1 * o2 < -1 and o3 * o4 < -1


class G:
    """A view's geometry, indexed."""

    def __init__(self, geo: dict):
        self.geo = geo
        self.view = geo.get("view", "")
        self.nodes = {n["id"]: n for n in geo["nodes"]}
        self.edges = geo["edges"]
        self.texts = geo.get("texts", [])
        self.markers = geo.get("markers", [])
        self.frames = geo.get("frames", [])
        self.rect = {i: rect(n) for i, n in self.nodes.items()}
        self.pipes = [e for e in self.edges if e["kind"] == "pipe"]
        self.into = {}
        self.outof = {}
        for e in self.pipes:
            self.into.setdefault(e["target"], []).append(e)
            self.outof.setdefault(e["source"], []).append(e)

    def kind(self, i) -> str:
        return self.nodes.get(i, {}).get("kind", "")

    def flows(self):
        """Each drawn flow: (valve, pipe in or None, pipe out or None), for a valve or disturbance."""
        for i, n in self.nodes.items():
            if n["kind"] in ("valve", "disturbance"):
                pin = (self.into.get(i) or [None])[0]
                pout = (self.outof.get(i) or [None])[0]
                if pin or pout:
                    yield n, pin, pout

    def flow_path(self, v, pin, pout) -> list:
        """The flow's whole way: its pipe in, through the valve, its pipe out."""
        a = pin["pts"] if pin else [centre(self.rect[v["id"]])]
        b = pout["pts"] if pout else [centre(self.rect[v["id"]])]
        return [tuple(p) for p in a] + [tuple(p) for p in b]


def inst(rule: Rule, score: float, what: str, parts: list, box: tuple, severity: str | None = None) -> dict:
    return {"rule": rule.name, "severity": severity or rule.severity, "score": round(float(score), 1), "what": what,
            "parts": parts, "box": [round(v) for v in box]}


# ------------------------------------------------------------------ the detectors, worst-looking first

def d_flow_excursion(r: Rule, g: G):
    """A flow whose way from end to end is far longer than the distance between its ends."""
    out = []
    for v, pin, pout in g.flows():
        if not (pin and pout):
            continue
        path = g.flow_path(v, pin, pout)
        L, D = length(path), manhattan(path[0], path[-1])
        if L > EXCURSION_K * D + EXCURSION_SLACK:
            ends = [pin["source"], pout["target"]]
            sev = "critical" if L - D > 300 else "major"
            out.append(inst(r, L - D, f"flow {v['label'] or v['id']}: {L:.0f}px of pipe between ends {D:.0f}px apart",
                            [v["id"], *ends], union(*(g.rect[x] for x in [v["id"], *ends] if x in g.rect)), sev))
    return out


def d_valve_between(r: Rule, g: G):
    """A valve that is not between the two things its flow joins."""
    out = []
    for v, pin, pout in g.flows():
        if not (pin and pout):
            continue
        a, b = tuple(pin["pts"][0]), tuple(pout["pts"][-1])
        vc = centre(g.rect[v["id"]])
        box = (min(a[0], b[0]) - VALVE_BOX_SLACK, min(a[1], b[1]) - VALVE_BOX_SLACK,
               max(a[0], b[0]) + VALVE_BOX_SLACK, max(a[1], b[1]) + VALVE_BOX_SLACK)
        off = math.hypot(max(0, box[0] - vc[0], vc[0] - box[2]), max(0, box[1] - vc[1], vc[1] - box[3]))
        if off > 0:
            ends = [pin["source"], pout["target"]]
            sev = "critical" if off > 120 else "major" if off > 40 else "minor"
            out.append(inst(r, off, f"valve {v['label'] or v['id']} {off:.0f}px outside the span of its ends",
                            [v["id"], *ends], union(g.rect[v["id"]], *(g.rect[x] for x in ends if x in g.rect)), sev))
    return out


def d_cloud_adjacent(r: Rule, g: G):
    """A cloud far from its valve."""
    out = []
    for v, pin, pout in g.flows():
        for p, c in ((pin, pin and pin["source"]), (pout, pout and pout["target"])):
            if not p or g.kind(c) != "cloud":
                continue
            d = gap(g.rect[c], g.rect[v["id"]])
            if d > CLOUD_GAP:
                sev = "critical" if d > CLOUD_FAR else "major" if d > 2 * CLOUD_GAP else "minor"
                out.append(inst(r, d, f"cloud of {v['label'] or v['id']} {d:.0f}px from its valve", [c, v["id"]],
                                union(g.rect[c], g.rect[v["id"]]), sev))
    return out


def d_through_part(r: Rule, g: G):
    """A line drawn through a part that is not one of its ends."""
    out = []
    for e in g.edges:
        ends = {e["source"], e["target"]}
        for i, rr in g.rect.items():
            if i in ends:
                continue
            inner = shrink(rr, 3)
            if inner[2] <= inner[0] or inner[3] <= inner[1]:
                continue
            L = sum(clip(a, b, inner) for a, b in segs(e["pts"]))
            if L > 4:
                pipe = e["kind"] == "pipe"
                sev = "critical" if pipe or g.kind(i) == "stock" else "major"
                out.append(inst(r, L, f"{e['kind']} {e['id']} through {i} for {L:.0f}px", [e["id"], i], rr, sev))
    return out


def d_part_overlap(r: Rule, g: G):
    """Two parts on top of each other."""
    out = []
    ids = list(g.rect)
    for k, i in enumerate(ids):
        for j in ids[k + 1:]:
            a = inter(shrink(g.rect[i], 2), shrink(g.rect[j], 2))
            if a > 0:
                out.append(inst(r, a, f"{i} on {j}", [i, j], union(g.rect[i], g.rect[j])))
    return out


def d_line_overlap(r: Rule, g: G):
    """Two lines (not of one net: not leaving one point, or arriving at one) on one track."""
    out = []

    def net(x, y):
        return ((x["sourcePort"] and x["sourcePort"] == y["sourcePort"]) or (x["targetPort"] and x["targetPort"] == y["targetPort"])
                or (x["kind"] == y["kind"] and (x["source"] == y["source"] or x["target"] == y["target"]))
                or (x["kind"] != "pipe" and y["kind"] != "pipe" and (
                    (x["source"] == y["source"] and g.kind(x["source"]) in ("valve", "disturbance")) or
                    (x["target"] == y["target"] and g.kind(x["target"]) in ("valve", "disturbance")))))
    ss = [(e, s) for e in g.edges for s in segs(e["pts"])]
    seen = set()
    for i in range(len(ss)):
        ea, (a, b) = ss[i]
        for j in range(i + 1, len(ss)):
            eb, (c, d) = ss[j]
            if ea is eb or net(ea, eb):
                continue
            ov = collinear_overlap(a, b, c, d)
            k = (ea["id"], eb["id"])
            if ov > OVERLAP_MIN and k not in seen:
                seen.add(k)
                sev = "critical" if ea["kind"] == "pipe" and eb["kind"] == "pipe" else "major"
                xs, ys = [a[0], b[0], c[0], d[0]], [a[1], b[1], c[1], d[1]]
                out.append(inst(r, ov, f"{ea['id']} on {eb['id']} for {ov:.0f}px", [ea["id"], eb["id"]],
                                (min(xs), min(ys), max(xs), max(ys)), sev))
    return out


def d_flow_bends(r: Rule, g: G):
    """A flow with more corners than it needs: one to or from a cloud straight, one between stocks a jog at most."""
    out = []
    for v, pin, pout in g.flows():
        path = g.flow_path(v, pin, pout)
        n = bends(path)
        ends = [x for x in (pin and pin["source"], pout and pout["target"]) if x]
        cloud = any(g.kind(x) == "cloud" for x in ends)
        back = len(path) > 1 and path[-1][0] < path[0][0] - 20          # a flow back (rework): it must turn
        allow = CLOUD_FLOW_BENDS if cloud else BACK_FLOW_BENDS if back else STOCK_FLOW_BENDS
        if n > allow:
            sev = "major" if n - allow >= 2 or cloud else "minor"
            xs, ys = [p[0] for p in path], [p[1] for p in path]
            out.append(inst(r, n - allow, f"flow {v['label'] or v['id']}: {n} bends ({allow} allowed)", [v["id"], *ends],
                            (min(xs), min(ys), max(xs), max(ys)), sev))
    return out


def d_cloud_side(r: Rule, g: G):
    """A cloud on the unnatural side of its valve: an outflow's cloud left of or above it, an inflow's right of or
    below it; or off the valve's line."""
    out = []
    for v, pin, pout in g.flows():
        vc = centre(g.rect[v["id"]])
        for p, c, outflow in ((pin, pin and pin["source"], False), (pout, pout and pout["target"], True)):
            if not p or g.kind(c) != "cloud":
                continue
            cc = centre(g.rect[c])
            dx, dy = cc[0] - vc[0], cc[1] - vc[1]
            if not outflow:
                dx, dy = -dx, -dy                      # (where the flow goes: from the cloud to the valve)
            way = "right" if abs(dx) >= abs(dy) and dx > 0 else "left" if abs(dx) >= abs(dy) else "down" if dy > 0 else "up"
            wrong = way in ("left", "up")
            misaligned = min(abs(dx), abs(dy)) > 6
            if wrong or misaligned:
                what = (f"{'outflow' if outflow else 'inflow'} cloud of {v['label'] or v['id']} runs {way}" +
                        (f", {min(abs(dx), abs(dy)):.0f}px off the valve's line" if misaligned else ""))
                out.append(inst(r, (40 if wrong else 0) + min(abs(dx), abs(dy)), what, [c, v["id"]],
                                union(g.rect[c], g.rect[v["id"]]), "major" if misaligned and min(abs(dx), abs(dy)) > 30 else "minor"))
    return out


def d_label_collision(r: Rule, g: G):
    """A word drawn over a line, a part or another word that is not its own."""
    out = []
    lines = [(e, s) for e in g.edges for s in segs(e["pts"])]
    for t in g.texts:
        tb = shrink(box4(t["box"]), 1)
        if tb[2] <= tb[0] or tb[3] <= tb[1]:
            continue
        own_node, own_edge = t.get("node"), t.get("edge")
        edge = next((e for e in g.edges if e["id"] == own_edge), None) if own_edge else None
        near = {own_node} | ({edge["source"], edge["target"]} if edge else set())
        if t.get("hull") and not own_node:
            continue                                  # (a frame's own title is checked against parts below)
        hit = 0.0
        what = []
        for e, (a, b) in lines:
            if own_edge and e["id"] == own_edge:
                continue
            L = clip(a, b, tb)
            if L > 3:
                hit += L
                what.append(e["id"])
        for i, rr in g.rect.items():
            if i in near:
                continue
            a = inter(tb, rr)
            if a > 0.15 * (tb[2] - tb[0]) * (tb[3] - tb[1]):
                hit += math.sqrt(a)
                what.append(i)
        if hit:
            sev = "minor" if len(t["text"]) <= 2 else "major"    # (a sign, a count: small, at a line's end)
            out.append(inst(r, hit, f"'{t['text']}' over {', '.join(dict.fromkeys(what))[:120]}",
                            [x for x in [own_node, own_edge] if x] + what[:3], tb, sev))
    # words over words (each pair once)
    ts = [t for t in g.texts if not t.get("hull")]
    for i in range(len(ts)):
        a = shrink(box4(ts[i]["box"]), 1)
        for j in range(i + 1, len(ts)):
            if ts[i].get("node") and ts[i].get("node") == ts[j].get("node"):
                continue
            if ts[i].get("edge") and ts[i].get("edge") == ts[j].get("edge"):
                continue
            if ts[i].get("marker") and ts[i].get("marker") == ts[j].get("marker"):
                continue
            b = shrink(box4(ts[j]["box"]), 1)
            ov = inter(a, b)
            small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
            if small > 0 and ov > 0.1 * small:
                sev = "minor" if min(len(ts[i]["text"]), len(ts[j]["text"])) <= 2 else "major"
                out.append(inst(r, 2 * math.sqrt(ov), f"'{ts[i]['text']}' on '{ts[j]['text']}'", [], union(a, b), sev))
    return out


def d_marker_collision(r: Rule, g: G):
    """A loop marker over a line or a part."""
    out = []
    for m in g.markers:
        mb = shrink(box4(m["box"]), 2)
        hit, what = 0.0, []
        for e in g.edges:
            L = sum(clip(a, b, mb) for a, b in segs(e["pts"]))
            if L > 3:
                hit += L
                what.append(e["id"])
        for i, rr in g.rect.items():
            if inter(mb, rr) > 4:
                hit += math.sqrt(inter(mb, rr))
                what.append(i)
        if hit:
            out.append(inst(r, hit, f"loop marker {m['loop']} over {', '.join(what)[:120]}", what[:3], mb))
    return out


def d_frame(r: Rule, g: G):
    """A part outside an open system it is in, or inside one it is not in; frames over each other (not nested)."""
    out = []
    names = {f["name"]: f for f in g.frames}
    fr = {f["name"]: (f["x"], f["y"], f["x"] + f["w"], f["y"] + f["h"]) for f in g.frames}
    for i, n in g.nodes.items():
        rr = g.rect[i]
        for s in n.get("systems") or []:
            f = fr.get(s) or fr.get("frame:" + s)
            if f and inter(rr, f) < (rr[2] - rr[0]) * (rr[3] - rr[1]) - 1:
                out.append(inst(r, 1, f"{i} outside its system {s}", [i], union(rr, f)))
        mine = set(n.get("systems") or []) | {"frame:" + s for s in n.get("systems") or []}
        for name, f in fr.items():
            if name in mine or name.startswith("casc:"):
                continue
            inside_it = any(s in fr and inter(fr[s], f) >= (fr[s][2] - fr[s][0]) * (fr[s][3] - fr[s][1]) - 1 for s in mine)
            if inter(shrink(rr, 2), f) > 0 and not inside_it:
                out.append(inst(r, math.sqrt(inter(rr, f)), f"{i} under the frame of {name}", [i], union(rr, f)))
    fl = list(fr.items())
    for k, (a, ra) in enumerate(fl):
        for b, rb in fl[k + 1:]:
            ov = inter(ra, rb)
            if ov <= 0:
                continue
            ina = ov >= (ra[2] - ra[0]) * (ra[3] - ra[1]) - 1
            inb = ov >= (rb[2] - rb[0]) * (rb[3] - rb[1]) - 1
            if not (ina or inb):
                out.append(inst(r, math.sqrt(ov), f"frames of {a} and {b} overlap", [], union(ra, rb)))
    del names
    return out


def d_line_bends(r: Rule, g: G):
    """Any other line with many corners."""
    out = []
    for e in g.edges:
        if e["kind"] == "pipe":
            continue
        n = bends(e["pts"]) if g.view != "dynamics" else len(e["pts"]) - 2
        if n > LINE_BENDS:
            xs, ys = [p[0] for p in e["pts"]], [p[1] for p in e["pts"]]
            out.append(inst(r, n - LINE_BENDS, f"{e['kind']} {e['id']}: {n} bends", [e["id"]], (min(xs), min(ys), max(xs), max(ys))))
    return out


def d_line_detour(r: Rule, g: G):
    """An information line (a connector, a signal, a process line) far longer than the way it covers."""
    out = []
    for e in g.edges:
        if e["kind"] == "pipe" or len(e["pts"]) < 2:
            continue
        L, D = length(e["pts"]), math.dist(e["pts"][0], e["pts"][-1])
        k, slack = (2.0, 240) if g.view == "blocks" else (CONNECTOR_DETOUR_K, CONNECTOR_DETOUR_SLACK)
        if L > k * D + slack:
            xs, ys = [p[0] for p in e["pts"]], [p[1] for p in e["pts"]]
            out.append(inst(r, L - D, f"{e['kind']} {e['id']}: {L:.0f}px for {D:.0f}px", [e["id"]],
                            (min(xs), min(ys), max(xs), max(ys)), "major" if L - D > 600 else "minor"))
    return out


def d_pipe_crossing(r: Rule, g: G):
    """Two flows crossing (a connector crossing a pipe is a hop, allowed)."""
    out = []
    ps = [(e, s) for e in g.pipes for s in segs(e["pts"])]
    seen = set()
    for i in range(len(ps)):
        ea, (a, b) = ps[i]
        for j in range(i + 1, len(ps)):
            eb, (c, d) = ps[j]
            if ea is eb or {ea["source"], ea["target"]} & {eb["source"], eb["target"]}:
                continue
            k = tuple(sorted((ea["id"], eb["id"])))
            if k not in seen and crosses(a, b, c, d):
                seen.add(k)
                out.append(inst(r, 1, f"{ea['id']} crosses {eb['id']}", list(k), union(seg_box(a, b), seg_box(c, d))))
    return out


def d_satellite_far(r: Rule, g: G):
    """A goal's desired level far from its gap, or a gap far from the valve it drives."""
    out = []
    for e in g.edges:
        if e["kind"] == "pipe":
            continue
        s, t = g.nodes.get(e["source"]), g.nodes.get(e["target"])
        if not s or not t:
            continue
        pair = (s.get("role") == "desired" and t.get("role") == "gap") or (s.get("role") == "gap" and t["kind"] in ("valve", "disturbance"))
        if not pair:
            continue
        d = gap(g.rect[s["id"]], g.rect[t["id"]])
        if d > SATELLITE_GAP:
            out.append(inst(r, d, f"{s['label']} {d:.0f}px from {t['label']}", [s["id"], t["id"]], union(g.rect[s["id"]], g.rect[t["id"]]),
                            "major" if d > 2 * SATELLITE_GAP else "minor"))
    return out


def d_stranded(r: Rule, g: G):
    """A part far from everything it is joined to."""
    out = []
    near: dict[str, float] = {}
    for e in g.edges:
        s, t = e["source"], e["target"]
        if s in g.rect and t in g.rect and s != t:
            d = gap(g.rect[s], g.rect[t])
            near[s] = min(near.get(s, 1e9), d)
            near[t] = min(near.get(t, 1e9), d)
    for i, d in near.items():
        if d > STRANDED_GAP and g.kind(i) != "system":
            out.append(inst(r, d, f"{i}: nothing it joins nearer than {d:.0f}px", [i], g.rect[i],
                            "major" if d > 2 * STRANDED_GAP else "minor"))
    return out


def d_fit(r: Rule, g: G):
    """A drawing far longer one way than the other that does not fit the screen at a legible zoom."""
    rs = list(g.rect.values()) + [(f["x"], f["y"], f["x"] + f["w"], f["y"] + f["h"]) for f in g.frames]
    if not rs:
        return []
    u = union(*rs)
    W, H = max(1, u[2] - u[0]), max(1, u[3] - u[1])
    cw, ch = g.geo.get("canvas", [0, 0, 1300, 800])[2:]
    fit = min((cw - 40) / W, (ch - 90) / H)
    aspect = max(W / H, H / W)
    if aspect > MAX_ASPECT and fit < MIN_FIT:
        return [inst(r, aspect, f"{W:.0f}x{H:.0f}: aspect {aspect:.1f}, fit {fit:.2f}", [], u)]
    return []


def d_valve_orientation(r: Rule, g: G):
    """A valve whose axis is not along its pipe: level while what it joins straight lies above or below it (or
    upright while that lies beside it), so the line zig-zags through it."""
    out = []
    for v, pin, pout in g.flows():
        turn = v.get("turn") or {"flow": "right"}
        level = turn.get("flow") in ("right", "left")
        vr = g.rect[v["id"]]
        vc = centre(vr)
        best = None                                   # the end most in line with the valve: it sets the axis
        for p, end in ((pin, pin and pin["source"]), (pout, pout and pout["target"])):
            if not p or end not in g.rect:
                continue
            er = g.rect[end]
            ec = centre(er)
            dx, dy = abs(ec[0] - vc[0]), abs(ec[1] - vc[1])
            beside = er[1] < vc[1] < er[3]           # its box spans the valve's centre one way or the other
            stacked = er[0] < vc[0] < er[2]
            if beside == stacked:
                continue
            off = dy if beside else dx
            if best is None or off < best[0]:
                best = (off, "level" if beside else "upright", end, dx if beside else dy)
        if best and best[3] > vr[3] - vr[1] and (best[1] == "level") != level:
            out.append(inst(r, best[3], f"valve {v['label'] or v['id']} {'level' if level else 'upright'}, its pipe to "
                            f"{best[2]} runs {'across' if best[1] == 'level' else 'up or down'}",
                            [v["id"], best[2]], union(vr, g.rect[best[2]])))
    return out


SIDE_CROWD = 2            # more pipes than this on one side of a stock, while a side facing one of their valves is free


def pipe_side(at, sr) -> str:
    """The side of a box a line's end meets."""
    return min((abs(at[0] - sr[0]), "left"), (abs(at[0] - sr[2]), "right"), (abs(at[1] - sr[1]), "up"), (abs(at[1] - sr[3]), "down"))[1]


def d_side_crowding(r: Rule, g: G):
    """Too many flows on one side of a stock while a side facing one of their valves has none."""
    out = []
    for sid, n in g.nodes.items():
        if n["kind"] != "stock":
            continue
        sr = g.rect[sid]
        sc = centre(sr)
        sides: dict[str, list] = {}
        for e in g.pipes:
            for end, other, at in ((e["source"], e["target"], e["pts"][0]), (e["target"], e["source"], e["pts"][-1])):
                if end == sid and other in g.rect:
                    sides.setdefault(pipe_side(at, sr), []).append(other)
        for side, others in sides.items():
            if len(others) <= SIDE_CROWD:
                continue
            free = []
            for o in others:
                oc = centre(g.rect[o])
                dx, dy = oc[0] - sc[0], oc[1] - sc[1]
                across = abs(dx) * (sr[3] - sr[1]) >= abs(dy) * (sr[2] - sr[0])     # (by the box's own shape)
                faces = ("right" if dx > 0 else "left") if across else ("down" if dy > 0 else "up")
                if faces != side and faces not in sides:
                    free.append((o, faces))
            if free:
                out.append(inst(r, len(others), f"{sid}: {len(others)} flows on its {side} side; its {free[0][1]} side, facing "
                                f"{free[0][0]}, has none", [sid, *others], union(sr, *(g.rect[o] for o in others))))
    return out


FEEDBACK_ROLES = {"sensor", "collector"}


def d_signal_backwards(r: Rule, g: G):
    """A forward signal in a block diagram drawn right to left (its target left of its source), so it wraps round:
    only the feedback path, through a sensor, runs back."""
    out = []
    for e in g.edges:
        s, t = g.nodes.get(e["source"]), g.nodes.get(e["target"])
        if not s or not t or s.get("role") in FEEDBACK_ROLES or t.get("role") in FEEDBACK_ROLES:
            continue
        if t.get("role") == "comparator" and s["kind"] in ("output", "port"):
            continue                                  # (an output fed back to a comparator: a feedback path)
        sc, tc = centre(g.rect[s["id"]]), centre(g.rect[t["id"]])
        back = sc[0] - tc[0]
        if back > 60 and length(e["pts"]) > manhattan(e["pts"][0], e["pts"][-1]) + 40:
            out.append(inst(r, back, f"{e['id']}: {back:.0f}px right to left, wrapping round", [e["id"], s["id"], t["id"]],
                            union(g.rect[s["id"]], g.rect[t["id"]]), "major" if back > 200 else "minor"))
    return out


RULES: list[Rule] = [
    Rule("flow-excursion", "critical", ("dynamics",), True, d_flow_excursion,
         "a flow's pipe at most 1.3x the distance between its ends, plus 80px"),
    Rule("line-through-part", "critical", ("dynamics", "blocks", "process"), True, d_through_part,
         "no line through a part that is not one of its ends"),
    Rule("part-overlap", "critical", ("dynamics", "blocks", "process"), True, d_part_overlap,
         "no part on another"),
    Rule("valve-between-ends", "critical", ("dynamics",), True, d_valve_between,
         "a valve inside the box its two ends span (grown by 30px)"),
    Rule("cloud-by-valve", "major", ("dynamics",), True, d_cloud_adjacent,
         "a cloud at most 70px from its valve"),
    Rule("line-overlap", "major", ("dynamics", "blocks", "process"), True, d_line_overlap,
         "no two lines (not one net) on one track for more than 20px"),
    Rule("frame-membership", "major", ("dynamics", "blocks", "process"), True, d_frame,
         "a part inside each open system it is in and no other; frames nest or stay apart"),
    Rule("flow-bends", "major", ("dynamics",), True, d_flow_bends,
         "a cloud's flow straight; a flow between stocks a jog at most (a flow back, 4 bends)"),
    Rule("label-collision", "major", ("dynamics", "blocks", "process"), True, d_label_collision,
         "no word over a line, a part or a word that is not its own"),
    Rule("valve-orientation-mismatch", "major", ("dynamics",), True, d_valve_orientation,
         "a valve's axis along its pipe: upright where what it joins in line lies above or below it"),
    Rule("side-crowding", "major", ("dynamics",), True, d_side_crowding,
         "at most 2 flows on one side of a stock while a side facing one of their valves is free"),
    Rule("cloud-side", "minor", ("dynamics",), True, d_cloud_side,
         "an outflow's cloud right of or below its valve, an inflow's left of or above it, on the valve's line"),
    Rule("marker-collision", "minor", ("dynamics",), True, d_marker_collision,
         "no loop marker over a line or a part"),
    Rule("pipe-crossing", "minor", ("dynamics",), True, d_pipe_crossing,
         "no two flows crossing"),
    Rule("signal-backwards", "minor", ("blocks",), True, d_signal_backwards,
         "a forward signal runs left to right; only a feedback path (through a sensor) runs back"),
    Rule("line-detour", "minor", ("dynamics", "blocks", "process"), True, d_line_detour,
         "an information line at most 2x its straight distance, plus 160px"),
    Rule("line-bends", "minor", ("dynamics", "blocks", "process"), True, d_line_bends,
         "an information line at most 6 bends"),
    Rule("satellite-far", "minor", ("dynamics",), True, d_satellite_far,
         "a goal's desired level and gap within 160px of each other and of the valve the gap drives"),
    Rule("stranded-part", "minor", ("dynamics", "blocks", "process"), True, d_stranded,
         "every part within 420px of something it is joined to"),
    Rule("fit", "minor", ("dynamics", "blocks", "process"), True, d_fit,
         "no drawing longer than 4x its width (or the other way) that does not fit at zoom 0.7"),
]
BY_NAME = {r.name: r for r in RULES}


def check(geo: dict, names: list[str] | None = None, fast: bool = False) -> list[dict]:
    """Every rule that applies to the view, over its geometry: the instances found."""
    g = G(geo)
    out = []
    for r in RULES:
        if (names and r.name not in names) or (fast and not r.fast) or g.view not in r.views:
            continue
        out += r.detect(r, g)
    return out
