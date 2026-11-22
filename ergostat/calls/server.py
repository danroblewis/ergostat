"""The engine's socket (``calls/``): a Unix socket in the state directory, readable and writable by its owner only.

One thread accepts; a fixed pool of ``WORKERS`` threads reads each request (one JSON line), answers it (one JSON line)
and closes it, so a thousand steps calling at once queue for the pool and never make a thread each. A call that has to
wait (``act`` for an approval, or for the engine to run what was approved) is **parked**: its connection is kept, its
thread given back, and one more thread looks at every parked call again whenever the record is written
(``notify.py``), answering each once it is settled or its wait is over."""

from __future__ import annotations

import json
import os
import queue
import socket
import tempfile
import threading
import time
from hashlib import sha256
from pathlib import Path

from . import POINTER, SOCKET, ops

WORKERS = 8
MOST = 4 * 1024 * 1024           # the largest request read (bytes)
LIMIT = 100                      # a socket's path is at most 104 bytes on macOS, 108 on Linux


def short() -> Path:
    """The folder of the short sockets, for state directories whose path is too long for one."""
    return Path(tempfile.gettempdir()) / f"ergostat-{os.getuid()}"


def path_for(state: Path, shard: str | None = None) -> Path:
    """Where the socket is: in the state directory (``engine.sock``; a shard's ``engine.SHARD.sock``, SPEC §9.8), or,
    when that path is too long for a socket, a short one named after the state directory and the shard (and written
    into the state directory, ``pointer_for``)."""
    p = Path(state) / (SOCKET if shard is None else f"engine.{shard}.sock")
    if len(str(p)) <= LIMIT:
        return p
    key = str(state) if shard is None else f"{state}\0{shard}"
    return short() / f"{sha256(key.encode()).hexdigest()[:16]}.sock"


def pointer_for(shard: str | None = None) -> str:
    """The file in the state directory naming its socket when it is not there (a shard's: ``engine.SHARD.sock.path``)."""
    return POINTER if shard is None else f"engine.{shard}.sock.path"


class Parked:
    def __init__(self, conn, cfg: dict, a: dict, end: float, ran_by: float):
        self.conn, self.cfg, self.a, self.end, self.ran_by = conn, cfg, a, end, ran_by


class Server:
    def __init__(self, eng):
        self.e = eng
        shard = getattr(eng, "shard", None)                    # (SPEC §9.8: each shard engine its own socket)
        self.path, self.pointer = path_for(eng.p.dir, shard), eng.p.dir / pointer_for(shard)
        self.sock: socket.socket | None = None
        self.jobs: queue.Queue = queue.Queue()
        self.parked: list[Parked] = []
        self.plock = threading.Lock()
        self.calls = 0
        self.keep = False                                      # closed to start again (cli/running.py): the file left

    # ---- listening

    def start(self) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o077)
        try:
            s.bind(str(self.path))
        finally:
            os.umask(old)
        s.listen(512)
        self.sock = s
        ptr = self.pointer
        if self.path.parent != self.e.p.dir:
            ptr.write_text(str(self.path))
        else:
            ptr.unlink(missing_ok=True)
        threading.Thread(target=self._accept, name="ergostat-socket", daemon=True).start()
        for i in range(WORKERS):
            threading.Thread(target=self._work, name=f"ergostat-socket-{i}", daemon=True).start()
        threading.Thread(target=self._parker, name="ergostat-socket-parked", daemon=True).start()
        return str(self.path)

    def close(self) -> None:
        with self.plock:                                       # (after it, nothing is queued behind the stop markers)
            s, self.sock = self.sock, None
        if s is not None:
            try:
                s.close()
            except OSError:
                pass
        for _ in range(WORKERS):
            self.jobs.put(None)
        if not self.keep:                                      # a restart's: left, so a run's call waits its whole bound
            self.remove()
        with self.plock:
            for w in self.parked:
                self._close(w.conn)
            self.parked = []

    def remove(self) -> None:
        self.path.unlink(missing_ok=True)
        self.pointer.unlink(missing_ok=True)

    def _accept(self) -> None:
        s = self.sock
        while not self.e.stop.is_set() and s is not None:
            try:
                conn, _ = s.accept()
            except OSError:
                return
            with self.plock:                                   # accepted as it closed: closed, so asked again
                if self.sock is None:
                    return self._close(conn)
                self.jobs.put(conn)

    def _work(self) -> None:
        while True:
            conn = self.jobs.get()
            if conn is None:
                return
            try:
                self._one(conn)
            except Exception as e:                             # one bad call never stops the others
                self._answer(conn, {"error": f"{type(e).__name__}: {e}"})

    # ---- one call

    def _one(self, conn) -> None:
        conn.settimeout(10.0)
        buf = b""
        while not buf.endswith(b"\n") and len(buf) < MOST:
            got = conn.recv(65536)
            if not got:
                break
            buf += got
        try:
            req = json.loads(buf)
            if not isinstance(req, dict):
                raise ValueError("a JSON object")
        except ValueError as e:
            return self._answer(conn, {"error": f"not a call ({e})"})
        self.calls += 1
        op = req.get("op")
        root = req.get("root")
        if root and Path(root).resolve() != Path(self.e.spec.root).resolve():   # another project's command: not ours
            return self._answer(conn, {"elsewhere": str(self.e.spec.root)})
        try:
            if op == "ping":
                e = self.e                              # (and how long since its last pass: the watchdog's measure)
                return self._answer(conn, {"ok": True, "project": e.spec.name, "pid": os.getpid(), "version": e.version,
                                           "passed": round(time.monotonic() - getattr(e, "passed_at", time.monotonic()), 2),
                                           "stalls": getattr(e.watchdog, "stalls", 0)})
            if op == "event":
                return self._answer(conn, ops.event(self.e, req))
            if op == "item":
                return self._answer(conn, ops.item(self.e, req))
            if op == "items":
                return self._answer(conn, ops.items(self.e, req))
            if op == "lease":
                return self._answer(conn, ops.lease(self.e, req))
            if op == "act":
                return self._act(conn, req)
        except ops.Refused as e:
            return self._answer(conn, {"error": str(e), "code": e.code})
        return self._answer(conn, {"error": f"no call {op!r} (event, act, lease, item, items, ping)"})

    def _act(self, conn, req: dict) -> None:
        from ..actions import program
        a, cfg = ops.act_start(self.e, req)
        end, ran_by = program.deadlines(self.e.spec, a, float(req.get("wait") or 0))
        a, done = program.settled(self.e.p, self.e.spec, cfg, a, end, ran_by)
        if done:
            return self._answer(conn, ops.act_answer(self.e, cfg, a))
        self._park([Parked(conn, cfg, a, end, ran_by)])        # it waits without a thread

    def _park(self, ws: list) -> None:
        with self.plock:                                       # (closed meanwhile: closed too, so asked again)
            if self.sock is not None:
                return self.parked.extend(ws)
        for w in ws:
            self._close(w.conn)

    def _parker(self) -> None:
        from ..actions import program
        from ..actions import record as rec
        from ..notify import of
        board = of(self.e.p.events)
        mark = board.n if board else 0
        while not self.e.stop.is_set() and self.sock is not None:
            if board is None:
                time.sleep(0.125)
            else:
                mark = board.wait(mark, 0.125)
            with self.plock:
                waiting, self.parked = self.parked, []
            if not waiting:
                continue
            still = []
            for w in waiting:
                try:
                    w.a, done = program.settled(self.e.p, self.e.spec, w.cfg, rec.get(self.e.p, w.a["id"]) or w.a,
                                                w.end, w.ran_by)
                    if done:
                        self._answer(w.conn, ops.act_answer(self.e, w.cfg, w.a))
                    else:
                        still.append(w)
                except Exception as e:
                    self._answer(w.conn, {"error": f"{type(e).__name__}: {e}"})
            self._park(still)

    @staticmethod
    def _answer(conn, out: dict) -> None:
        try:
            conn.sendall(json.dumps(out, default=str).encode() + b"\n")
        except OSError:
            pass
        Server._close(conn)

    @staticmethod
    def _close(conn) -> None:
        try:
            conn.close()
        except OSError:
            pass
