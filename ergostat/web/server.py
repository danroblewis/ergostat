"""The web page's HTTP server (standard library, bound to 127.0.0.1; read only but for the owner accepting or dismissing a
proposal, ``POST``). ``/`` is the page;
``/api/*`` returns what the command line shows, as JSON. The model is re-read when
``ergostat.toml`` changes, so the page follows the Supervisor's edits."""

from __future__ import annotations

import html
import json
import mimetypes
import secrets
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .. import graph, history, series
from .. import model as mdl
from .. import state as st
from ..series import off_stretches

STATIC = Path(__file__).parent / "static"
FILE_LIMIT = 20 * 1024 * 1024        # a file an item names is shown up to this size


def md_page(name: str, text: str) -> bytes:
    """A Markdown file opened in the browser, rendered with the page's own Markdown and styles: raw HTML in
    it is shown as text, never run; its relative links stay relative, so they open the files beside it."""
    data = json.dumps(text).replace("<", "\\u003c")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(name)}</title>
<link rel="stylesheet" href="/static/style.css"></head>
<body class="file-page"><main class="md" id="doc"></main>
<script src="/static/marked.min.js"></script><script src="/static/highlight.min.js"></script>
<script>
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}})[c]);
marked.use({{ renderer: {{ html: (t) => esc(typeof t === "string" ? t : t.text || "") }} }});
const el = document.getElementById("doc");
el.innerHTML = marked.parse({data});
for (const c of el.querySelectorAll("pre code")) {{ try {{ hljs.highlightElement(c); }} catch (e) {{}} }}
</script></body></html>""".encode()


class Live:
    """The project, with its model re-read when the file changes."""

    def __init__(self, project):
        import threading
        self.p = project
        self.mtime = self._mtime()
        self._lock = threading.Lock()
        self._snaps: dict = {}
        self._kept: dict = {}

    def cached(self, key):
        with self._lock:
            return self._kept.get(key)

    def keep(self, key, value) -> None:
        with self._lock:
            if len(self._kept) > 16:
                self._kept.clear()
            self._kept[key] = value

    def reloaded(self) -> None:
        """The model was changed here (a proposal accepted): take it as the one loaded."""
        self.mtime = self._mtime()
        history.note(self.p)

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
    """An answer; a graph's with its correspondence (``correspond.py``): which model parts each
    shape is, and which shapes stand for each part, so one selection is lit in every view."""
    got = _answer(live, path, q)
    if path.strip("/") == "graph" and isinstance(got, dict):
        from ..correspond import table
        got["corr"] = table(got, live.get().model)
    return got


def _answer(live: Live, path: str, q: dict):
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
    if head == "guide":                              # the Guide's frames: tiny models, the same for every project
        from ..guide import frames
        return frames()
    if head == "graph":
        system = one("system") or None
        around = one("around") or None
        from ..runner import running_pid
        att = st.attention(snap, bool(running_pid(p)) and snap["live"], m)
        if one("view") == "wiring":
            return {**graph.wiring(m, p, snap, graph.select(m, system, around, int(one("depth") or 1))), "attention": att}
        if one("view") == "blocks":                 # the control view: the whole control system as a block diagram
            from ..blockdiagram import diagram
            opened = q.get("open")
            want = None if opened is None else {x for x in (opened[0] or "").split(",") if x}
            return {**diagram(m, snap, want, system), "attention": att}
        from ..dynamics import attention as sd_attention
        from ..dynamics import dynamics, finish
        from ..fold import fold
        sd = one("view") == "dynamics"          # the system dynamics view: drawn from the same graph
        if sd:
            att = sd_attention(att, snap)       # (in its own words)
        tree = getattr(getattr(m, "spec", None), "systems", None)
        if tree and not around:              # systems as parts: boxed, opened, or drilled into (whatever it reaches outside)
            g = graph.control(m, snap, graph.select(m), graph.readings(p, at))
            opened = q.get("open")
            want = None if opened is None else {x for x in (opened[0] or "").split(",") if x}
            if sd:
                return {**finish(fold(dynamics(g, m), m, want, system)), "attention": att}
            return {**fold(g, m, want, system), "attention": att}
        sel = graph.select(m, system, around, int(one("depth") or 1))
        g = graph.control(m, snap, sel, graph.readings(p, at))
        return {**(dynamics(g, m) if sd else g), "attention": att}
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
            stretches = off_stretches(p, name, since, snap["at"])
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
                              machine=one("machine"), after_seq=int(after) if after else None, skip=skip,
                              **({"since": snap["at"] - snap["window"], "until": snap["at"]} if one("window") else {}))
    if head == "items":
        from ..spec import items as its
        spec = getattr(m, "spec", None)
        if name:
            return its.detail(p.events, spec, name, until=snap["at"])
        return its.listing(p.events, spec, kind=one("kind"), state=one("state"), until=snap["at"])
    if head == "series":                          # behaviour over time: each part's values, bucketed over the window
        refs = [r for r in (one("refs") or "").split(",") if r]
        out = series.series(p, snap, refs, int(one("points") or series.POINTS), bool(one("strip")))
        if one("replay"):                         # and what the model says: its replay, and its projection past now
            from .numbers_api import add_to_series
            add_to_series(live, p, snap, out, one("inputs") or "hold", one("whatif"),
                          "replay" if one("fan") == "replay" else bool(one("fan")))
        return out
    if head == "dominance":                       # which feedback loops drive the behaviour, and when (Loops That Matter)
        from .numbers_api import loop_dominance
        return loop_dominance(live, p, snap, int(one("points") or series.POINTS), one("loop"))
    if head == "whatif-fit":                      # a what-if's fit before anything is stored: per stock, and its payoff
        from .numbers_api import whatif_fit
        return whatif_fit(live, p, snap, one("whatif"))
    if head == "fit":                             # the Fit page: the replay against the record, its history, the proposals
        from .numbers_api import fit_page
        return fit_page(live, p, snap)
    if head == "loop-control":                    # the loop as a control engineer reads it: identified, analysed, monitored
        from .control_api import get as control
        return control(live, p, snap, one("goal") or "")
    if head == "loop-scope":
        return series.scope(p, snap, one("goal") or "", int(one("points") or series.POINTS))
    if head == "items-flow":
        return series.items_flow(p, snap, one("kind") or "", int(one("points") or series.POINTS))
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
            if pname in getattr(getattr(m, "spec", None), "auxiliaries", {}):
                from .numbers_api import part_numbers
                out["numbers"] = part_numbers(live, p, snap, "auxiliary", pname)
        elif kind in ("flow", "disturbance"):
            out["now"] = snap["flows"].get(pname)
            if getattr(m, "spec", None) is not None:
                from ..dynamics import equation
                from ..spec.findings import unit_of
                from ..spec.ir import Ref
                from .numbers_api import part_numbers
                out["equation"] = equation(m.spec, pname)
                out["unit"] = unit_of(m.spec, Ref("flow", pname))       # what moves: its own unit, else its stocks'
                out["numbers"] = part_numbers(live, p, snap, "flow", pname)
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
    token = secrets.token_urlsafe(24)                    # this run's: written into the page, asked of every write

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

        def _file(self, rel: str, page: bool = False):
            p = live.get()
            roots = [r.resolve() for r in (p.model.path.parent if p.model.path else None, p.dir) if r]
            for root in roots:
                f = (root / rel).resolve()
                if (root == f or root in f.parents) and f.is_file():
                    if f.stat().st_size > FILE_LIMIT:
                        return self._send(413, b"too big to show", "text/plain")
                    if page and f.suffix.lower() == ".md":     # opened in the browser: shown rendered, its relative links kept
                        return self._send(200, md_page(f.name, f.read_text(errors="replace")), "text/html; charset=utf-8")
                    return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            return self._send(404, b"not found", "text/plain")

        def _host_ok(self) -> bool:
            """Only a request addressed to this server by its own name: a page on another site whose
            name was pointed at 127.0.0.1 (DNS rebinding) sends its own name as the Host, and is refused."""
            port = self.server.server_address[1]
            return (self.headers.get("Host") or "").lower() in {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

        def do_POST(self):
            """The page's one kind of write: the owner accepting or dismissing a proposal, or asking for
            estimates. Only from the page itself: addressed to this server by its own name (the Host
            header), from its own origin (Origin, Sec-Fetch-Site), and carrying the token this run of the
            server wrote into the page it served, which no other page can read."""
            u = urlsplit(self.path)
            origin = self.headers.get("Origin")
            fetch_site = self.headers.get("Sec-Fetch-Site")
            if (not self._host_ok() or not u.path.startswith("/api/")
                    or (origin is not None and origin.lower() != f"http://{(self.headers.get('Host') or '').lower()}")
                    or (fetch_site is not None and fetch_site not in ("same-origin", "none"))
                    or not secrets.compare_digest(self.headers.get("X-Ergostat-Token") or "", token)):
                return self._send(403, b'{"error": "only the page may ask"}', "application/json")
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                self.rfile.read(min(n, 65536))
            from .numbers_api import post
            try:
                q = parse_qs(u.query)
                if u.path.startswith("/api/control/"):     # a loop's process, tuning or step test: the owner's answer
                    from .control_api import post as control
                    code, data = control(live, u.path.removeprefix("/api/"))
                else:
                    code, data = post(live, u.path.removeprefix("/api/"), _window(q), q)
            except Exception as e:                      # a broken request never takes the page down
                code, data = 500, {"error": f"{type(e).__name__}: {e}"}
            return self._send(code, json.dumps(data, default=str).encode(), "application/json")

        def do_GET(self):
            u = urlsplit(self.path)
            if not self._host_ok():                        # another site's name pointed here: nothing is read
                return self._send(403, b"not this server's name", "text/plain")
            if u.path.startswith("/api/"):
                try:
                    data = api(live, u.path.removeprefix("/api/"), parse_qs(u.query))
                except Exception as e:                  # a broken request never takes the page down
                    return self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode(), "application/json")
                if data is None:
                    return self._send(404, b'{"error": "not found"}', "application/json")
                return self._send(200, json.dumps(data, default=str).encode(), "application/json")
            if u.path == "/file":                          # a file an item names (file:PATH), from inside the project only
                return self._file((parse_qs(u.query).get("path") or [""])[0])
            if u.path.startswith("/file/"):                # the same, as a path: a Markdown file's relative links resolve
                navigating = "text/html" in (self.headers.get("Accept") or "") and "raw" not in parse_qs(u.query)
                return self._file(unquote(u.path.removeprefix("/file/")), page=navigating)
            name = "index.html" if u.path in ("/", "") else u.path.removeprefix("/static/")
            f = (STATIC / name).resolve()
            if STATIC.resolve() not in f.parents or not f.is_file():
                return self._send(404, b"not found", "text/plain")
            if name == "index.html":                       # the page carries this run's token for its writes
                body = f.read_bytes().replace(b'<meta charset="utf-8">',
                                              f'<meta charset="utf-8">\n<meta name="ergostat-token" content="{token}">'.encode(), 1)
                return self._send(200, body, "text/html; charset=utf-8")
            self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    Handler.live = live
    return Handler
