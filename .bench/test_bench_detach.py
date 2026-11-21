"""Throwaway: run-start latency and threads, main's pipe path against the branch's file path (not committed)."""
import statistics
import subprocess
import threading
import time
import types
from pathlib import Path

from ergostat.costs.sampler import Measured
from ergostat.spec import runrecord, stream

src = subprocess.run(["git", "show", "main:ergostat/spec/stream.py"], capture_output=True, text=True, check=True).stdout
oldmod = types.ModuleType("ergostat.spec.stream_main")
oldmod.__package__ = "ergostat.spec"
exec(compile(src, "stream_main.py", "exec"), oldmod.__dict__)


def old_run(cmd, d, i, first):
    t0 = time.perf_counter()
    p = Measured(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, start_new_session=True)
    oldmod.pump(p, "{}", None, lambda got: first.append(time.perf_counter() - t0) if len(first) == i else None)
    return time.perf_counter() - t0


def new_run(cmd, d, i, first):
    t0 = time.perf_counter()
    f = runrecord.files(d, f"r{i}")
    f["in"].write_text("{}")
    with open(f["in"], "rb") as fin, open(f["out"], "wb") as fout:
        p = Measured(runrecord.command(cmd, f), stdin=fin, stdout=fout, start_new_session=True)
    runrecord.write(f, p.pid, f"r{i}", "b", None, None)
    stream.follow(p, f["out"], None, lambda got: first.append(time.perf_counter() - t0) if len(first) == i else None)
    runrecord.remove(f)
    return time.perf_counter() - t0


def threads():
    return int(next(x for x in Path("/proc/self/status").read_text().splitlines() if x.startswith("Threads:")).split()[1])


def test_bench(tmp_path):
    out = []
    for name, fn in (("main", old_run), ("branch", new_run), ("main", old_run), ("branch", new_run)):
        first, total = [], []
        for i in range(30):
            total.append(fn("echo 1", tmp_path, i, first))
        peak, base = [0], threads()
        stop = threading.Event()

        def watch():
            while not stop.is_set():
                peak[0] = max(peak[0], threads())
                time.sleep(0.01)
        w = threading.Thread(target=watch)
        w.start()
        ts = [threading.Thread(target=fn, args=("sleep 1; echo 1", tmp_path, 100 + i, [])) for i in range(20)]
        t0 = time.perf_counter()
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        wall = time.perf_counter() - t0
        stop.set()
        w.join()
        out.append(f"{name}: first line median {statistics.median(first) * 1000:.1f} ms, run median "
                   f"{statistics.median(total) * 1000:.1f} ms (p90 {sorted(total)[26] * 1000:.1f}); 20 at once: "
                   f"{wall:.2f}s, threads {base} -> peak {peak[0]} (incl. 1 watcher)")
    print("\n".join(out))
