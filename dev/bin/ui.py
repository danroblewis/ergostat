"""The factory's page, apart from its engine, on the live version and on staging (the owner, 2026-11-22).

An engine restart no longer takes the page down, and a page change no longer waits for a drain:

- **real** (`[instance] port`): main as pushed. A change to page files is live on the next refresh. A change to the
  Python starts the new server beside the old one and moves the front to it once it answers.
- **staging** (`[instance] staging_port`, 8796): main plus every approved gap's reviewed commit, in rank order, a gap
  that conflicts left out and listed in `<live>/ui/staging.json`. It reads the factory's record and writes nothing: its
  front passes GET and HEAD only, and its server records no fits and refreshes no remotes.

    ui.py run      keep both up (one process, by a lock)
    ui.py ensure   start it in the background unless it is running
    ui.py status   what each serves"""

from __future__ import annotations

import fcntl
import http.client
import http.server
import json
import os
import re
import socket
import socketserver
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402
import live as lv  # noqa: E402

REAL_BACKENDS = (8791, 8792)
STAGING_BACKENDS = (8793, 8794)        # two, so a new server starts beside the one serving
STAGING_PORT = 8796
EVERY = 15                                   # seconds between looks at main and at the approved gaps
START_WAIT = 90                              # seconds a new server has to answer before the old one is kept
HOP = {"connection", "keep-alive", "proxy-connection", "te", "trailer", "transfer-encoding", "upgrade"}
STAGING_MAIN = """
import runpy, sys
import ergostat.web as web
import ergostat.remote.refresh as refresh
web.record_fits = lambda *a, **k: None
refresh.start = lambda *a, **k: None
sys.argv = ["ergostat", "-C", sys.argv[1], "web", "--port", sys.argv[2]]
runpy.run_module("ergostat", run_name="__main__")
"""


def needs_restart(names: list[str]) -> bool:
    """Whether a change reaches the server's Python; page files are read from disk at each request."""
    return any(n.endswith(".py") and n.startswith("ergostat/") or n in ("pyproject.toml", "uv.lock") for n in names)


def addressed(head: dict, port: int) -> dict:
    """A request made to this machine's front, as made to the server behind it: the server accepts only its own local
    address and an Origin that matches it. A public name (the tunnel's) is left as it came."""
    host = next((v for k, v in head.items() if k.lower() == "host"), "").lower()
    if not re.fullmatch(r"(127\.0\.0\.1|localhost|\[::1\]):\d+", host):
        return head
    here = f"127.0.0.1:{port}"
    out = {k: v for k, v in head.items() if k.lower() not in ("host", "origin")}
    out["Host"] = here
    if any(k.lower() == "origin" for k in head):
        out["Origin"] = f"http://{here}"
    return out


class Front(http.server.BaseHTTPRequestHandler):
    """Passes each request to the server now behind it, streaming the answer (the page's event stream never ends)."""
    protocol_version = "HTTP/1.1"
    backend = staticmethod(lambda: 0)
    writes = True

    def log_message(self, *a):
        pass

    def relay(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        if not self.writes and self.command not in ("GET", "HEAD"):
            return self.refuse(403, b"staging is read-only\n")
        port = self.backend()
        if not port:
            return self.refuse(503, b"the page is starting\n")
        head = addressed({k: v for k, v in self.headers.items() if k.lower() not in HOP}, port)
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=300)
            c.request(self.command, self.path, body=body, headers=head)
            r = c.getresponse()
        except OSError:
            return self.refuse(502, b"the page is restarting\n")
        try:
            self.send_response(r.status)
            for k, v in r.getheaders():
                if k.lower() not in HOP:
                    self.send_header(k, v)
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            while self.command != "HEAD":
                chunk = r.read1(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (OSError, http.client.HTTPException):
            self.close_connection = True
        finally:
            c.close()

    def refuse(self, code: int, text: bytes):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(text)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(text)
        self.close_connection = True

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = relay


class Listener(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128


def front(port: int, backend, writes: bool) -> Listener:
    handler = type("Bound", (Front,), {"backend": staticmethod(backend), "writes": writes})
    return Listener(("127.0.0.1", port), handler)


def front_when_free(port: int, backend, writes: bool) -> None:
    """Serve `port` as soon as it is free (an engine from before this split holds it until its next restart)."""
    while True:
        try:
            srv = front(port, backend, writes)
        except OSError:
            time.sleep(1)
            continue
        print(f"{time.strftime('%H:%M:%S')} front on {port}", flush=True)
        srv.serve_forever()


def answers(port: int) -> bool:
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", "/")
        ok = c.getresponse().status == 200
        c.close()
        return ok
    except OSError:
        return False


def free(port: int) -> bool:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


class Site:
    """One page: its tree, the server behind its front."""

    def __init__(self, cfg: dict, name: str, ports: tuple[int, ...], keep_address: str):
        self.cfg, self.name, self.ports, self.keep_address = cfg, name, ports, keep_address
        self.dir = lv.live(cfg) / "ui"
        self.tree = self.dir / name
        self.port, self.proc, self.sha = 0, None, ""
        if not (self.tree / ".git").exists():
            self.dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "-q", "--no-checkout", str(fac.path(cfg, "checkout")), str(self.tree)],
                           check=True)

    def git(self, *a, check=True):
        r = subprocess.run(["git", "-C", str(self.tree), "-c", "user.name=ui", "-c", "user.email=ui@localhost", *a],
                           capture_output=True, text=True, timeout=180)
        if check and r.returncode:
            raise RuntimeError(f"git {a[0]}: {r.stderr.strip()[-200:]}")
        return r.stdout.strip() if check else r.returncode

    def spawn(self, port: int):
        py = str(lv.live(self.cfg) / "current/.venv/bin/python")
        inst = str(lv.instance(self.cfg))
        args = [py, "-c", STAGING_MAIN, inst, str(port)] if self.name == "staging" else \
            [py, "-m", "ergostat", "-C", inst, "web", "--port", str(port)]
        log = open(self.dir / f"{self.name}.log", "a")
        return subprocess.Popen(args, env={**os.environ, "PYTHONPATH": str(self.tree), "PYTHONDONTWRITEBYTECODE": "1"},
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True, cwd=str(self.dir))

    def address_kept(self):
        """`ergostat web` writes its address where the factory's page is named: the front's stays there."""
        f = lv.state_dir(self.cfg) / "web.json"
        tmp = f.with_suffix(".ui")
        tmp.write_text(json.dumps({"url": self.keep_address}))
        tmp.replace(f)

    def serve_new(self) -> bool:
        port = next((p for p in self.ports if p != self.port and free(p)), 0)
        if not port:
            print(f"{self.name}: no free port", flush=True)
            return False
        new = self.spawn(port)
        end = time.time() + START_WAIT
        while time.time() < end and new.poll() is None and not answers(port):
            time.sleep(0.5)
        if new.poll() is not None or not answers(port):
            new.terminate()
            print(f"{self.name}: the new server did not answer; the old one stays", flush=True)
            return False
        self.address_kept()
        old, self.proc, self.port = self.proc, new, port
        if old:
            time.sleep(2)                        # requests under way on the old server finish
            old.terminate()
        return True

    def moved_to(self, sha: str, before: str) -> None:
        names = self.git("diff", "--name-only", before, sha).splitlines() if before else ["ergostat/x.py"]
        alive = self.proc is not None and self.proc.poll() is None
        if needs_restart(names) or not alive:
            self.serve_new()
        self.sha = sha
        print(f"{time.strftime('%H:%M:%S')} {self.name} at {sha[:10]}", flush=True)


def main_sha(cfg: dict) -> str:
    repo, base, remote = fac.path(cfg, "checkout"), cfg["git"]["base"], cfg["git"]["remote"]
    return fac.git(repo, "rev-parse", f"refs/remotes/{remote}/{base}")


def approved() -> list[dict]:
    return sorted(fac.items("gap", "approved"), key=lambda g: (float(g["fields"].get("rank") or 1e9), g["id"]))


def compose(site: Site, cfg: dict, main: str, gaps: list[dict]) -> dict:
    """main plus each approved gap's reviewed commit, on the staging tree."""
    import agents
    drop = str(agents.drop(cfg))
    site.git("fetch", "-q", str(fac.path(cfg, "checkout")), main)
    site.git("checkout", "-q", "--detach", "-f", main)
    site.git("clean", "-qfdx")
    took, left = [], []
    for g in gaps:
        sha = str(g["fields"].get("reviewed_head") or "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha) or site.git("fetch", "-q", drop, sha, check=False):
            left.append({"gap": g["id"], "why": "its reviewed commit is not in the drop"})
        elif site.git("merge", "-q", "--no-edit", "--no-ff", sha, check=False):
            site.git("merge", "--abort", check=False)
            site.git("reset", "-q", "--hard", check=False)
            left.append({"gap": g["id"], "why": "conflicts with what is ahead of it"})
        else:
            took.append(g["id"])
    return {"main": main, "tree": site.git("rev-parse", "HEAD"), "in": took, "left_out": left, "at": time.time()}


def run(cfg: dict) -> int:
    d = lv.live(cfg) / "ui"
    d.mkdir(parents=True, exist_ok=True)
    lock = open(d / "ui.lock", "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    (d / "ui.pid").write_text(str(os.getpid()))
    port = int(cfg["instance"]["port"])
    addr = f"http://127.0.0.1:{port}"
    real, staging = Site(cfg, "real", REAL_BACKENDS, addr), Site(cfg, "staging", STAGING_BACKENDS, addr)
    threading.Thread(target=front_when_free, args=(port, lambda: real.port, True), daemon=True).start()
    threading.Thread(target=front_when_free, args=(int(cfg["instance"].get("staging_port", STAGING_PORT)),
                                                   lambda: staging.port, False), daemon=True).start()
    seen = None
    while True:
        try:
            main = main_sha(cfg)
            if main != real.sha or real.proc is None or real.proc.poll() is not None:
                real.git("fetch", "-q", str(fac.path(cfg, "checkout")), main)
                before = real.sha
                real.git("checkout", "-q", "--detach", "-f", main)
                real.moved_to(main, before)
            gaps = approved()
            key = (main, tuple((g["id"], g["fields"].get("reviewed_head")) for g in gaps))
            if key != seen or staging.proc is None or staging.proc.poll() is not None:
                before = staging.sha
                got = compose(staging, cfg, main, gaps)
                (d / "staging.json").write_text(json.dumps(got, indent=1))
                staging.moved_to(got["tree"], before)
                seen = key
        except Exception as e:  # noqa: BLE001 - what is up stays up
            print(f"{time.strftime('%H:%M:%S')} pass failed: {e}", flush=True)
        time.sleep(EVERY)


def ensure(cfg: dict) -> None:
    d = lv.live(cfg) / "ui"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "ui.lock", "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
        except BlockingIOError:
            return                               # it is running
    log = open(d / "ui.log", "a")
    subprocess.Popen([sys.executable, __file__, "run"], stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     start_new_session=True, cwd=str(lv.instance(cfg)), env=os.environ.copy())


def main(argv: list[str]) -> int:
    cfg = fac.config()
    what = argv[0] if argv else "status"
    if what == "run":
        return run(cfg)
    if what == "ensure":
        ensure(cfg)
        return 0
    f = lv.live(cfg) / "ui" / "staging.json"
    print(f.read_text() if f.exists() else "staging not built")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
