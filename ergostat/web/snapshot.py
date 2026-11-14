"""The page as one file: every answer the page would ask the server for, taken now and written into
a copy of the page with its scripts and style inline. It opens anywhere, offline, with no ergostat
running: a diagram to attach to a document or a ticket, and everything behind it."""

from __future__ import annotations

import json
import re
import time
from urllib.parse import quote

from .server import STATIC, Live, api

SKIP = {"since", "at"}            # one window, one moment: the snapshot's own


def key(path: str, params: dict) -> str:
    """The lookup key for one request, the same as the page's (``util.js``)."""
    kept = sorted((k, str(v)) for k, v in params.items() if k not in SKIP and v not in (None, "", "undefined"))
    return path + ("?" + "&".join(f"{k}={v}" for k, v in kept) if kept else "")


def _requests(project) -> list[tuple[str, dict]]:
    m = project.model
    reqs: list[tuple[str, dict]] = [("status", {}), ("loops", {}), ("agents", {}), ("items", {}), ("residuals", {}),
                                    ("parts", {}), ("graph", {}), ("events", {"n": 300}), ("events", {"n": 60})]
    for view in ("control", "wiring"):
        for system in [None, *m.system_names()]:
            reqs.append(("graph", {"view": view, **({"system": system} if system else {})}))
    reqs += [(f"loops/{quote(n, safe='')}", {}) for n in m.controllers]
    reqs += [(f"agents/{quote(n, safe='')}", {}) for n in m.agents]
    for kind, table in m.tables().items():
        for n in table:
            k = "disturbance" if kind == "flow" and getattr(table[n], "disturbance", False) else kind
            reqs.append((f"part/{k}/{quote(n, safe='')}", {}))
    return reqs


def build(project, since: str = "1h") -> str:
    live = Live(project)
    data: dict = {"projects": []}
    for path, params in _requests(project):
        q = {"since": [since], **{k: [str(v)] for k, v in params.items()}}
        try:
            got = api(live, path, q)
        except Exception:                      # one part that cannot be answered leaves the rest
            got = None
        if got is not None:
            data[key(path, params)] = got
    for it in (data.get("items") or [])[:40]:
        got = api(live, f"items/{quote(it['item'], safe='')}", {"since": [since]})
        if got is not None:
            data[f"items/{quote(it['item'], safe='')}"] = got
    snap = {"at": time.time(), "since": since, "name": project.model.name, "data": data}

    def inline(text: str) -> str:
        return re.sub(r"</(script)", r"<\\/\1", text, flags=re.I)     # nothing in a script may close it early

    page = (STATIC / "index.html").read_text()
    page = page.replace('<link rel="stylesheet" href="/static/style.css">',
                        "<style>\n" + (STATIC / "style.css").read_text() + "\n</style>")
    snapshot_js = "window.SNAPSHOT = " + inline(json.dumps(snap, default=str)) + ";"

    def script(mt: re.Match) -> str:
        body = inline((STATIC / mt.group(1)).read_text())
        before = f"<script>{snapshot_js}</script>\n" if mt.group(1) == "elk.bundled.js" else ""
        return before + "<script>" + body + "</script>"
    return re.sub(r'<script src="/static/([\w.]+)"></script>', script, page)
