"""The worker's loop (SPEC §12s): ``hello`` first, a ``beat`` every 10 s, then each request line to the handler its
type names in ``HANDLERS``. A later part of the protocol is one module of its own and one line registering it here."""

import argparse
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import threading
import traceback

import frames
import keeper

WORKER = "1"
BEAT = 10.0
ROOT = "~/.local/state/ergostat-worker"
MOST_SLOTS = 64
HEX = set("0123456789abcdef")


class Refused(Exception):
    """The worker can't start as itself (its root or its node id unreadable): it says so and ends."""


def ping(req: dict, w: frames.Writer) -> None:
    w.send("pong", id=req["id"])


HANDLERS = {"ping": ping}


def node_id(root: str) -> str:
    """The node's random id, made once and kept in the root; two workers starting at once keep the same one."""
    path = os.path.join(root, "node")
    for _ in range(2):
        try:
            with open(path, encoding="ascii") as f:
                got = f.read().strip()
        except FileNotFoundError:
            got = None
        except (OSError, UnicodeDecodeError) as e:
            raise Refused(f"the node id can't be read: {e}") from None
        if got is not None:
            if len(got) == 32 and set(got) <= HEX:
                return got
            raise Refused(f"the node id in {path} is not 32 hex digits")
        tmp = os.path.join(root, f".node.{os.getpid()}")
        try:
            with open(tmp, "w", encoding="ascii") as f:
                f.write(secrets.token_hex(16) + "\n")
            try:
                os.link(tmp, path)              # (never over one another worker made meanwhile)
            except FileExistsError:
                pass
            finally:
                os.unlink(tmp)
        except OSError as e:
            raise Refused(f"the node id can't be kept: {e}") from None
    raise Refused("the node id could not be kept")


def cpus() -> int | None:
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count()


def memory() -> int | None:
    """Bytes of memory, or None when it can't be read (never a guess)."""
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    if sys.platform == "darwin":
        try:
            return int(subprocess.run(["/usr/sbin/sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                                      timeout=5).stdout)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return None


def disk_free(root: str) -> int | None:
    try:
        return shutil.disk_usage(root).free
    except OSError:
        return None


def labels(root: str) -> dict:
    """What the owner says the node has (``labels.json`` in the root: names to strings); unreadable, none."""
    try:
        with open(os.path.join(root, "labels.json"), encoding="utf-8") as f:
            got = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        got = None
    if isinstance(got, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in got.items()):
        return got
    print("ergostat worker: labels.json unreadable or not an object of strings: no labels said", file=sys.stderr)
    return {}


def hello(root: str) -> dict:
    n = cpus()
    return {"worker": WORKER, "node": node_id(root), "cpus": n, "memory": memory(), "disk": {"root": disk_free(root)},
            "arch": platform.machine(), "os": platform.system().lower(), "backends": [], "images": [],
            "labels": labels(root), "slots": min(n or 0, MOST_SLOTS), "runs": []}


def beats(w: frames.Writer, root: str, slots: int, every: float, stop: threading.Event) -> None:
    while not stop.wait(every):
        try:
            w.send("beat", free=slots, disk={"root": disk_free(root)}, runs={})
        except (OSError, ValueError):
            stop.set()


def the_root(given: str | None) -> str:
    root = os.path.abspath(given) if given else os.path.expanduser(ROOT)
    if not os.path.isabs(root):                 # (no home to put it in: never the folder it was started in)
        raise Refused(f"no root: {ROOT} has no home here; give --root DIR")
    try:
        os.makedirs(root, mode=0o700, exist_ok=True)
    except OSError as e:
        raise Refused(f"the root {root} can't be made: {e}") from None
    return root


def serve(root: str, inp, w: frames.Writer, every: float) -> int:
    said = hello(root)
    w.send("hello", **said)
    HANDLERS.update(keeper.handlers(root, said))
    stop = threading.Event()
    threading.Thread(target=beats, args=(w, root, said["slots"], every, stop), daemon=True).start()
    want = 1
    try:
        while not stop.is_set():
            line = inp.readline(frames.MAX + 1)
            if not line:
                return 0
            try:
                req = frames.decode(line, want)
            except frames.Bad as e:
                w.send("error", id=e.id, why=e.why)
                return 1
            want += 1
            if not isinstance(req.get("id"), str | int) or isinstance(req["id"], bool):
                w.send("error", id=None, why=f"{req['type']}: a request carries an id (a string or an integer)")
                continue
            handler = HANDLERS.get(req["type"])
            if handler is None:
                w.send("error", id=req["id"], why=f"unknown type {req['type']!r}")
                continue
            try:
                handler(req, w)
            except Exception as e:              # (one request's fault, said; the next is still served)
                traceback.print_exc(file=sys.stderr)
                w.send("error", id=req["id"], why=f"{req['type']} failed: {type(e).__name__}")
        return 1
    finally:
        stop.set()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ergostat worker", description="A compute node's worker: the protocol on "
                                 "standard input and output (SPEC §12s)")
    ap.add_argument("--stdio", action="store_true", required=True, help="speak the protocol on stdin and stdout")
    ap.add_argument("--root", metavar="DIR", help=f"the worker's own folder (default {ROOT})")
    ap.add_argument("--beat", type=float, default=BEAT, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if not 0.05 <= args.beat <= 60:
        print("ergostat worker: --beat is between 0.05 and 60 seconds", file=sys.stderr)
        return 2
    w = frames.Writer(sys.stdout.buffer)
    try:
        return serve(the_root(args.root), sys.stdin.buffer, w, args.beat)
    except Refused as e:
        w.send("error", id=None, why=str(e))
        return 1
    except BrokenPipeError:
        return 1
