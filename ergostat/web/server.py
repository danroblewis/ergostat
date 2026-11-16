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

from .. import graph, history
from .. import model as mdl
from .. import state as st

STATIC = Path(__file__).parent / "static"


class Live:
    """The project, with its model re-read when the file changes."""

    def __init__(self, project):
        import threading
        self.p = project
        self.mtime = self._mtime()
        self._lock = threading.Lock()
        self._snaps: dict = {}

    def _mtime(self):
        return mdl.stamp(self.p.model)

    def snapshot(self, p, window: float, at: float | None):
        """The state, shared by the requests of one moment: the page asks for several parts of it
        every few seconds, and each would otherwise estimate it all again. Kept 1.5s; a past
        moment (``at``) is kept until the model changes."""
        key = (window, at, self.mtime)
        with self._lock:
            got = self._snaps.get(key)
            if got and (at is not None or time.time() - got[0] < 1.5):
                return got[1]
        snap = st.snapshot(p, window, at)
        with self._lock:
            if len(self._snaps) > 32:
                self._snaps.clear()
            self._snaps[key] = (time.time(), snap)
        return snap

    def get(self):
        now = self._mtime()
        if now != self.mtime:
            try:
                self.p.model = mdl.load(self.p.model.path.parent)
                self.mtime = now
                history.note(self.p)
            except Exception:
                pass                                   # keep the last model that loaded
        return self.p


def _window(q) -> float:
    from ..durations import parse_duration
    try:
        return parse_duration(q["since"][0]) if q.get("since") else st.WINDOW
    except ValueError:
        return st.WINDOW


def _tail(path, n: int) -> list[str]:
    """The last ``n`` lines of a file, read from its end."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 65536))
            return f.read().decode(errors="replace").splitlines()[-n:]
    except OSError:
        return []


def api(live: Live, path: str, q: dict):
    p = live.get()
    m = p.model
    one = lambda k: (q.get(k) or [None])[0]       # noqa: E731
    parts = path.strip("/").split("/")
    head, name = parts[0], unquote(parts[1]) if len(parts) > 1 else None
    at = None
    if one("at"):
        try:
            at = float(one("at"))
        except ValueError:
            at = None
    snap = live.snapshot(p, _window(q), at)
    if head == "status":
        from ..runner import running_pid
        running = bool(running_pid(p))
        return {"name": m.name, "running": running, "live": snap["live"], "first": p.events.first_time(),
                "attention": st.attention(snap, running and snap["live"], m), "loops": snap["loops"],
                "counts": {"loops": len(m.controllers), "stocks": len(m.stocks), "flows": len(m.flows),
                           "agents": len(m.agents), "events": p.events.count(), "measurements": p.measurements.count()},
                "systems": m.system_names(), "check": [{"level": lv, "message": msg} for lv, msg in mdl.check(m)],
                "at": snap["at"], "window": snap["window"],
                "changes": [{"time": e["time"], **{k: e["data"][k] for k in ("added", "removed", "changed")}}
                            for e in history.changes(p, snap["at"] - snap["window"])][-5:]}
    if head == "projects":
        from ..projects import known
        return known()
    if head == "graph":
        system = one("system") or None
        around = one("around") or None
        from ..runner import running_pid
        att = st.attention(snap, bool(running_pid(p)) and snap["live"], m)
        if one("view") == "wiring":
            return {**graph.wiring(m, p, snap, graph.select(m, system, around, int(one("depth") or 1))), "attention": att}
        from ..fold import fold
        tree = getattr(getattr(m, "spec", None), "systems", None)
        if tree and not around:              # systems as parts: boxed, opened, or drilled into (whatever it reaches outside)
            g = graph.control(m, snap, graph.select(m), graph.readings(p, at))
            opened = q.get("open")
            want = None if opened is None else {x for x in (opened[0] or "").split(",") if x}
            return {**fold(g, m, want, system), "attention": att}
        sel = graph.select(m, system, around, int(one("depth") or 1))
        return {**graph.control(m, snap, sel, graph.readings(p, at)), "attention": att}
    if head == "systems":
        return [{"name": s, "description": m.systems[s].description if s in m.systems else "",
                 "parts": len(m.members(s)), "loops": [n for n in snap["loops"] if n in m.members(s)]}
                for s in m.system_names()]
    if head == "loops":
        if name:
            lp = snap["loops"].get(name)
            if lp is None:
                return None
            since = snap["at"] - snap["window"]
            stock_pts = st.history(p, lp["stock"], since, snap["at"])
            step = max(1, len(stock_pts) // 300)
            # the whole window, reduced: every opening's time thinned evenly, the off stretches from every crossing
            openings = sorted(({"time": e["time"], "amount": e["data"].get("amount"), "valve": e["item"]}
                               for v in lp["valves"] for e in p.events.query(n=None, type="valve.opened", item=v, since=since,
                                                                               until=snap["at"])), key=lambda o: o["time"])
            n_open = len(openings)
            openings = openings[::max(1, n_open // 300)]
            crossings = p.events.query(n=None, item=name, type="loop.*", until=snap["at"], unvoided=True)
            stretches, off_from = [], None
            for e in crossings:
                if e["type"] == "loop.off" and off_from is None:
                    off_from = max(e["time"], since)
                elif e["type"] == "loop.holding" and off_from is not None:
                    if e["time"] > since:
                        stretches.append([off_from, e["time"]])
                    off_from = None
            if off_from is not None:
                stretches.append([off_from, snap["at"]])
            in_window = [e for e in crossings if e["time"] >= since]
            c = m.controllers[name]
            agent = lambda a: ({"name": a, "kind": m.agents[a].kind, "rung": m.agents[a].rung}       # noqa: E731
                               if a in m.agents else None)
            parts = []
            for s_ in lp["sensors"]:
                got = p.measurements.latest(f"sensor/{s_}", snap["at"])
                parts.append({"kind": "sensor", "name": s_, "agent": agent(m.sensors[s_].agent),
                              "last": {"time": got[0], "value": got[1]} if got else None})
            parts.append({"kind": "controller", "name": name, "agent": agent(c.agent), "open_loop": c.open_loop,
                          "last": lp["last_decision"]})
            for v in lp["valves"]:
                parts.append({"kind": "valve", "name": v, "agent": agent(m.valves[v].agent), "mode": m.valves[v].mode,
                              "max": m.valves[v].max, "last": p.events.last_opening(v, snap["at"])})
            return {**lp, "points": stock_pts[::step], "openings": openings, "openings_total": n_open,
                    "since": since, "until": snap["at"], "off_stretches": stretches,
                    "crossings": in_window[-20:], "crossings_total": len(in_window),
                    "description": c.description, "parts": parts,
                    "rates": {f: snap["flows"].get(f, {}).get("rate") for f in lp["flows"]},
                    "decisions": st.decisions(p, name, since, snap["at"]),
                    "hints": [h for h in snap["hints"] if h["controller"] == name]}
        return snap["loops"]
    if head == "agents":
        if name:
            a = m.agents.get(name)
            if a is None:
                return None
            runs = [e for e in p.events.query(n=400, item=name, type="agent.*", until=snap["at"])
                    if e["type"] in ("agent.ran", "agent.failed")]
            from ..runner import log_path
            log = log_path(p, name)
            return {"agent": {**a.__dict__, "rung": a.rung}, **snap["agents"][name], "recent": runs[-80:],
                    "log": _tail(log, 40), "log_path": str(log),
                    "loads": [f.name for f in m.flows.values() if f.disturbance and f.agent == name]}
        return {n: {**a, "hints": [h for h in snap["hints"] if h["agent"] == n]} for n, a in snap["agents"].items()}
    if head == "events":
        after = one("after")
        skip = () if one("runs") or one("type") else ("agent.started", "agent.ran")   # as `ergostat event`
        return p.events.query(n=int(one("n") or 100), type=one("type"), item=one("item"), source=one("source"),
                              after_seq=int(after) if after else None, skip=skip)
    if head == "items":
        from ..spec import items as its
        spec = getattr(m, "spec", None)
        if name:
            return its.detail(p.events, spec, name, until=snap["at"])
        return its.listing(p.events, spec, kind=one("kind"), state=one("state"), until=snap["at"])
    if head == "residuals":
        return snap["residuals"]
    if head == "parts":
        rd = graph.readings(p, at)
        agent = lambda n: ({"name": n, "kind": m.agents[n].kind, "rung": m.agents[n].rung} if n in m.agents else None)  # noqa: E731
        return {
            "stock": [{"name": n, "value": snap["stocks"][n]["value"], "unit": x.unit, "points": snap["stocks"][n]["points"][-40:],
                       "sensor": snap["stocks"][n]["sensor"], "inflow": snap["stocks"][n]["inflow"],
                       "outflow": snap["stocks"][n]["outflow"],
                       "systems": x.systems} for n, x in m.stocks.items()],
            "flow": [{"name": n, "from": x.source, "to": x.target, "rate": snap["flows"][n]["rate"], "how": snap["flows"][n]["how"],
                      "valve": snap["flows"][n]["valve"]} for n, x in m.flows.items() if not x.disturbance],
            "disturbance": [{"name": n, "from": x.source, "to": x.target, "rate": snap["flows"][n]["rate"], "how": snap["flows"][n]["how"],
                             "estimated": snap["flows"][n]["estimated"]} for n, x in m.flows.items() if x.disturbance],
            "valve": [{"name": n, "flow": x.flow, "mode": x.mode, "agent": agent(x.agent), "position": rd.get(f"valve/{n}"),
                       "last": (snap["flows"].get(x.flow, {}).get("openings") or {}).get("last"),
                       "rate": snap["flows"].get(x.flow, {}).get("rate")} for n, x in m.valves.items()],
            "sensor": [{"name": n, "measures": x.measures, "agent": agent(x.agent), "reading": rd.get(n),
                        "at": (p.measurements.latest(f"sensor/{n}") or (None,))[0]} for n, x in m.sensors.items()],
            "controller": [{"name": n, "holds": x.holds, "setpoint": x.setpoint, "status": snap["loops"][n]["status"],
                            "agent": agent(x.agent), "open_loop": x.open_loop} for n, x in m.controllers.items()],
            "system": [{"name": s_, "description": m.systems[s_].description if s_ in m.systems else "", "parts": len(m.members(s_)),
                        "loops": [n for n in snap["loops"] if n in m.members(s_)],
                        "off": [n for n in snap["loops"] if n in m.members(s_) and snap["loops"][n]["status"] in ("off", "open")]}
                       for s_ in m.system_names()],
        }
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
            rd = p.measurements.range(f"sensor/{pname}", snap["at"] - snap["window"], snap["at"])
            out["now"] = {"readings": rd[-60:], "count": len(rd)}
        elif kind == "valve":
            out["now"] = {"openings": p.events.query(n=300, type="valve.opened", item=pname),
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
        timeout = 10                                   # an idle browser connection gives its thread back
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
