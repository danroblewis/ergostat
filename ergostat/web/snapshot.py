"""The page as one file: every answer the page would ask the server for, taken now and written into
a copy of the page with its scripts and style inline. It opens anywhere, offline, with no ergostat
running: a diagram to attach to a document or a ticket, and everything behind it."""

from __future__ import annotations

import base64
import json
import re
import time
from urllib.parse import quote

from .. import series
from . import snapshot_sets
from .server import STATIC, Live, api

SKIP = {"since", "at"}            # one window, one moment: the snapshot's own


def key(path: str, params: dict) -> str:
    """The lookup key for one request, the same as the page's (``util.js``)."""
    kept = sorted((k, str(v)) for k, v in params.items() if k not in SKIP and v not in (None, "", "undefined"))
    return path + ("?" + "&".join(f"{k}={v}" for k, v in kept) if kept else "")


def _q(name: str) -> str:
    """As the page's encodeURIComponent: it leaves !'()* alone."""
    return quote(name, safe="!'()*")


def _requests(project) -> list[tuple[str, dict]]:
    m = project.model
    reqs: list[tuple[str, dict]] = [("status", {}), ("loops", {}), ("agents", {}), ("daemons", {}), ("items", {}), ("items-overview", {}),
                                    ("residuals", {}), ("fit", {}), ("parts", {}), ("guide", {}), ("graph", {}),
                                    ("events", {"n": 80}), ("events", {"n": 80, "runs": 1})]
    for view in ("dynamics", "control", "blocks", "process"):
        for system in [None, *m.system_names()]:
            reqs.append(("graph", {"view": view, **({"system": system} if system else {})}))
            if view in ("dynamics", "control", "blocks") and getattr(m, "spec", None) is not None:   # every system opened
                reqs.append(("graph", {"view": view, "open": "*", **({"system": system} if system else {})}))
    reqs += [(f"loops/{_q(n)}", {}) for n in m.controllers]
    reqs += [(f"agents/{_q(n)}{f}", {}) for n in m.agents for f in ("", "/files")]
    # the charts' series: each part's strip, each loop's scope, each item kind's flow (charts.js asks the same)
    pts = {"points": series.POINTS}
    reqs += [("series", {"refs": f"{series.kind_of(m, n)}.{n}", "strip": 1, "replay": 1, **pts}) for n in [*m.stocks, *m.flows]]
    reqs += [("loop-scope", {"goal": n, **pts}) for n in m.controllers]
    if getattr(m, "spec", None) is not None:
        reqs.append(("dominance", pts))                  # which feedback loops drive the behaviour, for every loop's panel
        reqs += [("loop-control", {"goal": n}) for n in m.spec.goals]   # each loop as a control engineer reads it
    reqs += [("items-flow", {"kind": k, **pts}) for k in (getattr(getattr(m, "spec", None), "items", None) or {})]
    reqs += [(f"kinds/{_q(k)}", {}) for k in (getattr(getattr(m, "spec", None), "items", None) or {})]   # what each touches
    for kind, table in m.tables().items():
        for n in table:
            k = "disturbance" if kind == "flow" and getattr(table[n], "disturbance", False) else kind
            reqs.append((f"part/{k}/{_q(n)}", {}))
    return reqs


def _graphs(listed: dict) -> list[dict]:
    """The Items page's Graph and Timeline requests (``pages.js``), from its ``items`` answer: per system, its kinds
    with relations or named by one (no kind chosen), and each kind alone, related or not (one chosen)."""
    rel = {n for k in listed.get("kinds") or [] for ts in (k.get("relations") or {}).values() for n in (k["name"], *ts)}
    out: dict[str, dict] = {}
    for g in listed.get("systems") or [{"kinds": [k["name"] for k in listed.get("kinds") or []]}]:
        want = [n for n in g.get("kinds") or [] if n in rel]
        for kinds in ([",".join(want)] if want else []) + want:
            out[kinds] = {"kinds": kinds}
    for k in listed.get("kinds") or []:
        out.setdefault(k["name"], {"kinds": k["name"]})
    return list(out.values())


def _states(own: dict, kind: str) -> list[str]:
    """A chosen kind's states, from its own answer (``items?kind=K``; the no-kind list is cut at its newest per
    kind): each it declares and each it counts an item in. No answer of its own: none (each left out)."""
    k = next((x for x in own.get("kinds") or [] if x["name"] == kind), {})
    return [s for s in dict.fromkeys([*(k.get("states") or []), *(k.get("counts") or {})]) if s]


def _strip(x) -> None:
    """Every ``unread_lines`` (lines an agent printed that were not understood) taken out, wherever it is."""
    if isinstance(x, dict):
        x.pop("unread_lines", None)
        for v in x.values():
            _strip(v)
    elif isinstance(x, list):
        for v in x:
            _strip(v)


def build(project, since: str = "1h", logs: bool = False) -> str:
    """``logs``: the end of each agent's log goes in too (left out by default: a log may hold what
    should not be sent on)."""
    live = Live(project)
    data: dict = {"projects": []}
    def ask(path: str, params: dict) -> None:
        q = {"since": [since], **{k: [str(v)] for k, v in params.items()}}
        try:
            got = api(live, path, q)
        except Exception:                      # one part that cannot be answered leaves the rest
            got = None
        if got is not None:
            if path.startswith("agents/") and not logs:
                got["log"] = ["(left out of this snapshot: ergostat snapshot --with-logs puts it in)"]
                got.pop("log_path", None)
            data[key(path, params)] = got
    for path, params in _requests(project):
        ask(path, params)
    if isinstance(data.get("loops"), dict):     # the Loops page's one answer: each goal's summary from its analysis above
        from .control_api import summary
        data[key("loops", {"perf": 1})] = {n: {**lp, "perf": summary(data[c]) if (c := key("loop-control", {"goal": n})) in data
                                               else None} for n, lp in data["loops"].items()}
    for k in (data.get("items") or {}).get("kinds") or []:      # a kind chosen, and each of its states
        ask("items", {"kind": k["name"]})
        for st in _states(data.get(key("items", {"kind": k["name"]})) or {}, k["name"]):
            ask("items", {"kind": k["name"], "state": st})
    for params in _graphs(data.get("items") or {}):
        ask("items-graph", params)
    snapshot_sets.hold(data, lambda q: api(live, "items", {"since": [since], **q}))   # the sets its panels link to
    for it in ((data.get("items") or {}).get("items") or [])[:40]:
        got = api(live, f"items/{_q(it['id'])}", {"since": [since]})
        if got is not None:
            data[f"items/{_q(it['id'])}"] = got
    if not logs:                                  # what an agent printed but ergostat could not read is its log too
        _strip(data)
    snap = {"at": time.time(), "since": since, "name": project.model.name, "data": data}

    def inline(text: str) -> str:
        text = re.sub(r"</(script)", r"<\\/\1", text, flags=re.I)    # nothing in a script may close it early,
        text = re.sub(r"<(script)", r"\\x3c\1", text, flags=re.I)    # nor look like one opening (in a string or regex, \x3c is <)
        return text.replace("<!--", "<\\!--")                          # nor open a comment that hides its end

    page = (STATIC / "index.html").read_text()
    page = page.replace('<link rel="stylesheet" href="/static/style.css">',
                        "<style>\n" + (STATIC / "style.css").read_text() + "\n</style>")
    # every < in the data as \u003c: no tag, comment or script end can form inside the script
    snapshot_js = "window.SNAPSHOT = " + json.dumps(snap, default=str).replace("<", "\\u003c") + ";"

    def script(mt: re.Match) -> str:
        body = inline((STATIC / mt.group(1)).read_text())
        before = f"<script>{snapshot_js}</script>\n" if mt.group(1) == "elk.bundled.js" else ""
        if mt.group(1) == "avoid.js":             # the line router too, as data: a page opened from a file cannot fetch it
            lib = STATIC / "libavoid"
            before += ("<script>window.LIBAVOID = " + json.dumps({"js": base64.b64encode((lib / "libavoid.js").read_bytes()).decode(),
                       "wasm": base64.b64encode((lib / "libavoid.wasm").read_bytes()).decode()}) + ";</script>\n")
        return before + "<script>" + body + "</script>"
    return re.sub(r'<script src="/static/([\w./]+)"></script>', script, page)
