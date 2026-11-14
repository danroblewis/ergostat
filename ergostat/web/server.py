"""The web page's HTTP server (standard library, read only, bound to 127.0.0.1). ``/`` is the page;
``/api/*`` returns what the command line shows, as JSON. The model is re-read when
``ergostat.toml`` changes, so the page follows the Supervisor's edits."""

from __future__ import annotations

import json
import mimetypes
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .. import graph
from .. import model as mdl
from .. import state as st

STATIC = Path(__file__).parent / "static"


class Live:
    """The project, with its model re-read when the file changes."""

    def __init__(self, project):
        self.p = project
        self.mtime = self._mtime()

    def _mtime(self):
        try:
            return self.p.model.path.stat().st_mtime if self.p.model.path else 0
        except OSError:
            return 0

    def get(self):
        now = self._mtime()
        if now != self.mtime:
            try:
                self.p.model = mdl.load(self.p.model.path.parent)
                self.mtime = now
            except Exception:
                pass                                   # keep the last model that loaded
        return self.p


def _window(q) -> float:
    from ..durations import parse_duration
    try:
        return parse_duration(q["since"][0]) if q.get("since") else st.WINDOW
    except ValueError:
        return st.WINDOW


def api(live: Live, path: str, q: dict):
    p = live.get()
    m = p.model
    one = lambda k: (q.get(k) or [None])[0]       # noqa: E731
    parts = path.strip("/").split("/")
    head, name = parts[0], unquote(parts[1]) if len(parts) > 1 else None
    snap = st.snapshot(p, _window(q))
    if head == "status":
        from ..runner import running_pid
        return {"name": m.name, "running": bool(running_pid(p)), "attention": st.attention(snap), "loops": snap["loops"],
                "counts": {"loops": len(m.controllers), "stocks": len(m.stocks), "flows": len(m.flows),
                           "agents": len(m.agents), "events": p.events.count(), "measurements": p.measurements.count()},
                "systems": m.system_names(), "check": [{"level": lv, "message": msg} for lv, msg in mdl.check(m)],
                "at": snap["at"], "window": snap["window"]}
    if head == "graph":
        system = one("system") or None
        around = one("around") or None
        sel = graph.select(m, system, around, int(one("depth") or 1))
        if one("view") == "wiring":
            return graph.wiring(m, p, snap, sel)
        return graph.control(m, snap, sel)
    if head == "systems":
        return [{"name": s, "description": m.systems[s].description if s in m.systems else "",
                 "parts": len(m.members(s)), "loops": [n for n in snap["loops"] if n in m.members(s)]}
                for s in m.system_names()]
    if head == "loops":
        return snap["loops"]
    if head == "agents":
        if name:
            a = m.agents.get(name)
            if a is None:
                return None
            runs = [e for e in p.events.query(n=200, item=name, type="agent.*") if e["type"] in ("agent.ran", "agent.failed")]
            from ..runner import log_path
            log = log_path(p, name)
            return {"agent": {**a.__dict__, "rung": a.rung}, **snap["agents"][name], "recent": runs[-20:],
                    "log": log.read_text(errors="replace").splitlines()[-40:] if log.exists() else []}
        return snap["agents"]
    if head == "events":
        after = one("after")
        return p.events.query(n=int(one("n") or 100), type=one("type"), item=one("item"), source=one("source"),
                              after_seq=int(after) if after else None)
    if head == "items":
        if name:
            evs = p.events.query(n=None, item=name)
            fields = {}
            for e in evs:
                fields.update(e["data"])
            return {"item": name, "fields": fields, "events": evs[-200:]}
        return p.events.items()[:200]
    if head == "residuals":
        return snap["residuals"]
    if head == "part":
        kind = name
        pname = unquote(parts[2]) if len(parts) > 2 else None
        table = m.tables().get("flow" if kind == "disturbance" else kind)
        if table is None or pname not in table:
            return None
        x = table[pname]
        out = {"kind": x.kind if not getattr(x, "disturbance", False) else "disturbance", "model": x.__dict__}
        if kind == "stock":
            out["now"] = snap["stocks"].get(pname)
        elif kind in ("flow", "disturbance"):
            out["now"] = snap["flows"].get(pname)
        elif kind == "sensor":
            out["now"] = {"readings": p.measurements.range(f"sensor/{pname}", time.time() - snap["window"])[-60:]}
        elif kind == "valve":
            out["now"] = {"openings": p.events.query(n=20, type="valve.opened", item=pname),
                          "flow": snap["flows"].get(x.flow)}
        elif kind == "controller":
            out["now"] = {"loop": snap["loops"].get(pname),
                          "decisions": p.events.query(n=20, type="controller.decided", item=pname)}
        agent = getattr(x, "agent", None)
        if agent and agent in m.agents:
            out["agent"] = {"name": agent, "kind": m.agents[agent].kind, "rung": m.agents[agent].rung}
        return out
    return None


def handler(project):
    live = Live(project)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlsplit(self.path)
            if u.path.startswith("/api/"):
                try:
                    data = api(live, u.path.removeprefix("/api/"), parse_qs(u.query))
                except Exception as e:                  # a broken request never takes the page down
                    return self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode(), "application/json")
                if data is None:
                    return self._send(404, b'{"error": "not found"}', "application/json")
                return self._send(200, json.dumps(data, default=str).encode(), "application/json")
            name = "index.html" if u.path in ("/", "") else u.path.removeprefix("/static/")
            f = (STATIC / name).resolve()
            if STATIC.resolve() not in f.parents or not f.is_file():
                return self._send(404, b"not found", "text/plain")
            self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    return Handler
