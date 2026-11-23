"""The engine's session with each node of the model's pools (SPEC §12s.4): one ``Node`` per entry of a pool, named
``POOL/N`` by its place in the list and never by its host. A node's session is a subprocess (``ssh -T -o
BatchMode=yes HOST ergostat worker --stdio``, or the pool's ``connect:`` argv) spoken to over its pipes by one reader
thread, which also keeps the beat deadline and reconnects with backoff. A ``connect:`` session's standard error is
kept in the pool's log; an ``ssh:`` session's never is (ssh names the HostName, address and user its config gives),
only its exit status. A node is in service only after a ``hello`` of protocol 1 whose labels
include the pool's; lost after three beats missed or the session's end, whichever first. Only a session that held
three beats starts the backoff again, so a worker that says hello and dies is tried at growing waits, said once.
A second thread per node pings it every 2 s while it is in service; ``least_rtt`` is the least round trip of the
window, and ``Pools.status`` each pool's nodes in service, out, slots, free, last error and least round trip."""

from __future__ import annotations

import dataclasses
import itertools
import os
import re
import selectors
import signal
import subprocess
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

from .compile import MAX_NODES, MAX_SLOTS
from .worker import frames

BEAT = 10.0                     # the worker's beat (serve.BEAT)
MISSED = 3                      # beats missed before a node is lost: 30 s
FIRST, MOST = 1.0, 600.0        # reconnects: from 1 s, doubling, to ten minutes
TIMEOUT = 30.0                  # a request's answer, unless the caller says
LOG_MOST, ERR_MOST = 8 << 20, 1 << 20   # a pool's log before it turns over to .1; a session's stderr kept (its tail)
SOURCE = "ergostat"
PING, RTTS = 2.0, 300           # a ping every 2 s while in service; the round trips kept (10 minutes of them)
ERRS = itertools.count(1)       # the order errors were set in, over every node (never by their times)
BAD = frozenset({"line over 1 MiB", "not JSON", "not a JSON object", "no type"})   # frames.Bad's fixed reasons


class Lost(Exception):
    """The node is not in service, or its session ended before the answer came."""


def backoff(tries: int, first: float = FIRST) -> float:
    return min(MOST, first * 2 ** min(tries, 30))


def argv_of(entry: dict) -> list[str]:
    if "ssh" in entry:                  # (a Host name compile checked: letters, digits, . _ -, never an option)
        return ["ssh", "-T", "-o", "BatchMode=yes", entry["ssh"], "ergostat", "worker", "--stdio"]
    return list(entry["connect"])


class Node:
    def __init__(self, pool, n: int, log: Path, record, beat: float = BEAT, first: float = FIRST, ping: float = PING):
        entry = pool.nodes[n - 1]
        self.name, self.argv, self.want = f"{pool.name}/{n}", argv_of(entry), dict(pool.labels)
        self.ssh = "ssh" in entry
        self.log, self.record, self.beat, self.first = log, record, beat, first
        self.state, self.error, self.hello, self.tries, self.said = "connecting", None, None, 0, None
        self.since, self.steady, self.told, self.upsaid = None, False, False, False     # (see _hello and _steady)
        self.lock, self.closed = threading.Lock(), threading.Event()
        self.proc: subprocess.Popen | None = None
        self.rc: int | None = None                      # the last session's exit status
        self.w: frames.Writer | None = None
        self.pending: dict[int, list] = {}              # request id → [answered, the answer]
        self.ids = itertools.count(1)
        self.handlers: dict[str, list] = {}
        self.thread = threading.Thread(target=self._run, name=f"ergostat-node-{self.name}", daemon=True)
        self.every, self.rtts, self.free, self.erred = ping, deque(maxlen=RTTS), None, 0   # (rtts: (when, seconds))
        self.pinger = threading.Thread(target=self._ping, name=f"ergostat-ping-{self.name}", daemon=True)

    def start(self) -> Node:
        self.thread.start()
        self.pinger.start()
        return self

    def alive(self) -> bool:
        return self.thread.is_alive() or self.pinger.is_alive()

    def least_rtt(self, window: float = 60.0) -> float | None:
        """The least round trip (s) of the pongs heard in the last ``window`` seconds of this session; None before
        the first."""
        now = time.monotonic()
        with self.lock:
            return min((r for at, r in self.rtts if now - at <= window), default=None)

    def reading(self) -> dict:
        """What the pool's status takes from this node: a node out of service gives no slots and nothing free."""
        rtt = self.least_rtt()
        with self.lock:
            up, h = self.state == "in-service", self.hello or {}
            slots = h.get("slots", 0) if up else 0
            free = self.free if up and type(self.free) is int and 0 <= self.free <= slots else 0   # (unsaid: none)
            return {"up": up, "slots": slots, "free": free, "error": self.error, "erred": self.erred, "rtt": rtt}

    def on(self, type: str, fn) -> None:
        """``fn(node, frame)`` for each frame of ``type`` that answers no request, called on the reader thread."""
        with self.lock:
            self.handlers.setdefault(type, []).append(fn)

    def request(self, msg: dict, timeout: float = TIMEOUT) -> dict:
        """Send ``msg`` (its ``type`` and fields) with a new ``id``; the frame answering it. Lost when the node is out of
        service or its session ends first; TimeoutError past ``timeout``."""
        fields = {k: v for k, v in msg.items() if k not in ("type", "v", "seq", "id")}
        slot = [threading.Event(), None]
        with self.lock:
            if self.state != "in-service" or self.w is None:
                raise Lost(f"{self.name}: {self.state}")
            rid, w = next(self.ids), self.w
            self.pending[rid] = slot
        try:
            w.send(msg["type"], id=rid, **fields)
        except (OSError, ValueError) as e:
            with self.lock:
                self.pending.pop(rid, None)
            if isinstance(e, OSError) or w.out.closed:
                raise Lost(f"{self.name}: the session ended") from None
            raise                                       # (the caller's frame: over 1 MiB, or not JSON)
        if not slot[0].wait(timeout):
            with self.lock:
                self.pending.pop(rid, None)
            raise TimeoutError(f"{self.name}: no answer to {msg['type']} in {timeout:g} s")
        if slot[1] is None:
            raise Lost(f"{self.name}: the session ended")
        return slot[1]

    def status(self) -> dict:
        with self.lock:
            h = self.hello or {}
            return {"node": self.name, "state": self.state, "error": self.error, "slots": h.get("slots", 0)}

    def close(self) -> None:
        """Ends the session (its process group killed) and stops reconnecting; ``thread`` ends soon after."""
        self.closed.set()
        with self.lock:                                 # (under the lock: never a group already reaped)
            _signal(self.proc)

    # ---- the reader thread

    def _run(self) -> None:
        while not self.closed.is_set():
            self.since, self.steady, self.told = None, False, False
            try:
                state, why = self._session()
            except Exception as e:                      # (any fault, a temp file's too: lost, said, tried again)
                state, why = "lost", f"the session failed: {type(e).__name__}"
            if self.steady:                             # (a session that held: its next hello is said at once)
                self.upsaid = False
            self._out(state, why)
            if self.closed.wait(backoff(self.tries, self.first)):
                break
            self.tries += 1
        with self.lock:
            self.state = "closed"

    def _session(self) -> tuple[str, str]:
        err, self.rc = (None if self.ssh else tempfile.TemporaryFile()), None    # (what ssh says: never kept)
        try:
            with self.lock:
                if self.closed.is_set():
                    return "closed", "closed"
                try:
                    self.proc = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                 stderr=err or subprocess.DEVNULL,
                                                 start_new_session=True)
                except OSError as e:
                    return "lost", f"could not start: {e.strerror or type(e).__name__}"
                self.w = frames.Writer(self.proc.stdin)
            try:
                return self._read(self.proc.stdout.fileno())
            finally:
                self._end()
        finally:
            self._keep(err)

    def _read(self, fd: int) -> tuple[str, str]:
        buf, want, heard = b"", 1, time.monotonic()
        sel = selectors.DefaultSelector()               # (never select(): it can't take an fd past 1023)
        sel.register(fd, selectors.EVENT_READ)
        try:
            while not self.closed.is_set():
                left = heard + MISSED * self.beat - time.monotonic()
                if left <= 0:
                    return "lost", f"{MISSED} beats missed"
                if self.since is not None and not self.steady and time.monotonic() - self.since >= MISSED * self.beat:
                    self._steady()
                if not sel.select(min(left, 0.5)):
                    continue
                got = os.read(fd, 1 << 16)
                if not got:
                    return "lost", "the session ended"
                heard, buf = time.monotonic(), buf + got
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if (why := self._line(line, want)) is not None:
                        return ("refused" if want == 1 else "lost"), why
                    want += 1
                if len(buf) > frames.MAX:
                    return ("refused" if want == 1 else "lost"), "a line over 1 MiB"
            return "closed", "closed"
        finally:
            sel.close()

    def _line(self, line: bytes, want: int) -> str | None:
        try:
            f = frames.decode(line, want)
        except frames.Bad as e:
            return f"line {want}: {_bad(e.why)}"
        except Exception:                               # (RecursionError on JSON nested deep enough)
            return f"line {want}: not JSON"
        if want == 1:
            return self._hello(f)
        rid = f.get("id")
        with self.lock:
            slot = self.pending.pop(rid, None) if type(rid) is int else None
            fns = list(self.handlers.get(f["type"], ()))
        if slot is not None:
            slot[1] = f
            slot[0].set()
        elif f["type"] == "beat":
            with self.lock:
                self.free = f.get("free")
        for fn in () if slot is not None else fns:
            try:
                fn(self, f)
            except Exception as e:                      # (a handler's fault is its own: the session goes on)
                self._note(f"{f['type']} handler failed: {type(e).__name__}")
        return None

    def _hello(self, f: dict) -> str | None:
        if f["type"] == "error":                        # (its words can name the remote user's home: never kept)
            return "the worker refused; its reason is not kept"
        if f["type"] != "hello":
            return "its first line is not hello"
        said = f.get("labels") if isinstance(f.get("labels"), dict) else {}
        lacks = sorted(k for k, v in self.want.items() if said.get(k) != v)
        if lacks:
            return f"its labels lack the pool's {', '.join(lacks)}"
        if type(f.get("slots")) is not int or not 0 <= f["slots"] <= MAX_SLOTS:
            return f"its slots are not 0 to {MAX_SLOTS}"
        with self.lock:
            self.hello, self.state, self.error, self.since = f, "in-service", None, time.monotonic()
            self.told = not self.upsaid                # (a retry of a session that had a hello: said once it holds)
            self.upsaid = True
        if self.told:
            self._up()
        return None

    def _steady(self) -> None:
        """In service for three beats: the backoff starts at its first wait again and any reason may be said anew."""
        with self.lock:
            self.steady, self.tries, self.said, tell, self.told = True, 0, None, not self.told, True
        if tell:
            self._up()

    def _up(self) -> None:
        self.record("compute.node.up", {"node": self.name, "slots": self.hello["slots"]}, f"{self.name}: in service")

    def _end(self) -> None:
        with self.lock:
            p, self.proc, self.w, pending, self.pending = self.proc, None, None, self.pending, {}
        _signal(p)
        self.rc = p.wait()
        for s in (p.stdin, p.stdout):
            try:
                s.close()
            except OSError:
                pass
        for slot in pending.values():
            slot[0].set()                               # (no answer: Lost)

    def _out(self, state: str, why: str) -> None:
        with self.lock:
            if self.closed.is_set():
                return
            self.state, self.error, self.hello, self.free, self.erred = state, why, None, None, next(ERRS)
            self.rtts.clear()                           # (the round trips of a session ended: never the next one's)
            new, self.said = self.said != (state, why), (state, why)
        if new:                                         # (once, not each try of a node that stays down)
            self.record(f"compute.node.{state}", {"node": self.name, "why": why}, f"{self.name}: {state} ({why})")

    def _ping(self) -> None:
        while not self.closed.wait(self.every):
            with self.lock:
                h = self.hello if self.state == "in-service" else None
            if h is None:
                continue
            t = time.monotonic()
            try:
                got = self.request({"type": "ping"})
            except (Lost, TimeoutError):
                continue
            except Exception as e:                      # (said; the pings go on)
                self._note(f"ping failed: {type(e).__name__}")
                continue
            now = time.monotonic()
            with self.lock:
                if got.get("type") == "pong" and self.hello is h:     # (still the session it was sent on)
                    self.rtts.append((now, now - t))

    def _keep(self, err) -> None:
        if err is None:                                 # an ssh session: its exit status alone, never its words
            if self.rc is not None:
                self._note(f"ssh exited {self.rc}; its standard error is not kept")
            return
        try:
            size = os.fstat(err.fileno()).st_size
            text = os.pread(err.fileno(), ERR_MOST, max(0, size - ERR_MOST)).decode(errors="replace")
        except OSError:
            return
        finally:
            err.close()
        for line in text.splitlines():
            self._note(line)

    def _note(self, line: str) -> None:
        try:
            if self.log.exists() and self.log.stat().st_size > LOG_MOST:
                os.replace(self.log, self.log.with_suffix(".log.1"))
            with open(self.log, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {self.name} {line}\n")
        except OSError:
            pass


def _bad(why: str) -> str:
    """A bad frame's reason as kept: only the forms frames.decode writes, with numbers; nothing the worker wrote."""
    if why in BAD or re.fullmatch(r"protocol v\d{1,9} is not v\d{1,9}|seq \d{1,18} where \d{1,18} was next", why):
        return why
    return "its protocol is not v1" if why.startswith("protocol") else "its seq is out of order"


def _signal(p: subprocess.Popen | None) -> None:
    if p is not None and p.returncode is None:
        try:
            os.killpg(p.pid, signal.SIGKILL)            # (the session's whole group: ssh, or the worker and its own)
        except (ProcessLookupError, PermissionError):
            pass


class Pools:
    """The engine's nodes: ``sync`` to the model's pools (a pool changed or removed is closed, a new one started),
    ``close`` to end them all. At most 64 nodes, counting those still closing."""

    def __init__(self, p, say, beat: float = BEAT, first: float = FIRST):
        self.p, self.say, self.beat, self.first = p, say, beat, first
        self.defs: dict = {}
        self.nodes: dict[str, Node] = {}
        self.draining: list[Node] = []
        self.lock = threading.Lock()

    def sync(self, pools: dict) -> None:
        want = {n: dataclasses.replace(c, where=None, description="") for n, c in pools.items()}
        with self.lock:
            for name in [n for n in self.defs if want.get(n) != self.defs[n]]:
                del self.defs[name]
                for k in [k for k in self.nodes if k.startswith(name + "/")]:
                    self.nodes[k].close()
                    self.draining.append(self.nodes.pop(k))
            self.draining = [n for n in self.draining if n.alive()]
            for name, c in want.items():
                if name in self.defs:
                    continue
                if len(self.nodes) + len(self.draining) + len(c.nodes) > MAX_NODES:
                    self.say(f"compute {name}: not connected: past {MAX_NODES} nodes, counting those closing")
                    continue
                self.defs[name] = c
                logs = Path(self.p.dir) / "logs"
                logs.mkdir(parents=True, exist_ok=True)
                for i in range(1, len(c.nodes) + 1):
                    node = Node(c, i, logs / f"compute.{name}.log", self._record, self.beat, self.first)
                    self.nodes[node.name] = node.start()

    def close(self, wait: float = 5.0) -> None:
        with self.lock:
            every, self.nodes, self.defs = list(self.nodes.values()) + self.draining, {}, {}
            self.draining = every
        for n in every:
            n.close()
        end = time.monotonic() + wait
        for n in every:
            n.thread.join(max(0.0, end - time.monotonic()))
            n.pinger.join(max(0.0, end - time.monotonic()))

    def status(self) -> dict:
        """Each pool's status, by name: ``in_service`` and ``lost`` (every node not in service, one still connecting
        too), the ``slots`` and ``free`` of those in service, the last ``error`` set on a node still out of service
        (``{node, why}``, or None) and the least round trip (s) of the last 60 s over its nodes. Nodes as POOL/N only."""
        with self.lock:
            pools = {name: {k: n for k, n in self.nodes.items() if k.startswith(name + "/")} for name in self.defs}
        out = {}
        for name, nodes in pools.items():
            got = {k: n.reading() for k, n in nodes.items()}
            up = [r for r in got.values() if r["up"]]
            bad = max(((r["erred"], k, r["error"]) for k, r in got.items() if not r["up"] and r["error"]), default=None)
            rtt = min((r["rtt"] for r in up if r["rtt"] is not None), default=None)
            out[name] = {"in_service": len(up), "lost": len(got) - len(up), "slots": sum(r["slots"] for r in up),
                         "free": sum(r["free"] for r in up), "error": bad and {"node": bad[1], "why": bad[2]},
                         "least_rtt": None if rtt is None else round(rtt, 6)}
        return out

    def _record(self, kind: str, data: dict, said: str) -> None:
        self.say(f"compute {said}")
        try:
            self.p.events.add(kind, source=SOURCE, data=data)
        except Exception as e:                          # (the session goes on; what failed is said)
            self.say(f"compute: recording {kind}: {type(e).__name__}")
