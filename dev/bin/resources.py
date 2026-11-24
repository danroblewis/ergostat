"""The machine's resources (dev/model/resources.yaml): `resources.py NAME` prints one reading (a sensor), and
`resources.py line` the status line.

Every reading comes from one snapshot (run/resources/snapshot.json), taken under a lock at most every 25 s, and the
slow ones (Docker's disk, the factory's folders, the Docker VM's open files: slow.json) at most every 10 minutes;
each command under a timeout, a reading it cannot give left out (its sensor then fails, and goes stale). macOS (sysctl, vm_stat, iostat,
top, lsof) or Linux (/proc).
Sizes are in GB of 2^30 bytes, CPU in cores, utilisation a share.

session-headroom is how many more sessions fit: the least, over host CPU, host memory, the Docker VM's CPU and memory,
of (setpoint x capacity - in use) / one session's use (the median measured peak of a session and of a suite, from
run/resources/sessions.jsonl; [resources] defaults until three are measured), and 0 while disk or threads are past
their goal. The setpoints are the goals' holds in dev/model/resources.yaml, the one place they are written."""

from __future__ import annotations

import fcntl
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402

PREFIX = "ergostat-factory-"
FAST, SLOW, GB = 25.0, 600.0, 2**30
UNITS = {"b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12, "kib": 2**10, "mib": 2**20, "gib": 2**30, "tib": 2**40}
GOALS = {"cpu": "cpu-within", "memory": "memory-within", "vm-memory": "vm-memory-within", "disk": "disk-free-enough",
         "threads": "threads-within"}


def sh(*cmd: str, timeout: float = 10) -> str:
    """A command's output; '' when it fails or runs past its timeout."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout if r.returncode == 0 else ""


def size_gb(text: str) -> float:
    """Docker's sizes ("553.4MiB", "22.7GB", "0B") in GB."""
    m = re.search(r"([\d.]+)\s*([kKMGT]?i?B)", text or "")
    return float(m[1]) * UNITS[m[2].lower()] / GB if m else 0.0


def memory(total: float, used: float, pressure: float | None) -> dict:
    return {"memory-total": round(total / GB, 2), "memory-used": round(used / GB, 2),
            "memory-free": round((total - used) / GB, 2), "memory-utilisation": round(used / total, 3),
            "memory-pressure": pressure}


# ---- macOS

def mac_memory(memsize: str, vm_stat: str, level: str) -> dict:
    """Used as Activity Monitor counts it: app memory (anonymous less purgeable), wired, and compressed; pressure from
    kern.memorystatus_level (the share of memory available)."""
    page = int(re.search(r"page size of (\d+)", vm_stat)[1])
    p = {k.strip('"').lower(): int(v) for k, v in re.findall(r"^(.+?):\s+(\d+)\.?\s*$", vm_stat, re.M)}
    pages = (p.get("anonymous pages", p.get("pages active", 0)) - p.get("pages purgeable", 0)
             + p.get("pages wired down", 0) + p.get("pages occupied by compressor", 0))
    return memory(float(memsize), pages * page, round(1 - int(level) / 100, 3) if level.strip() else None)


def iostat_cpu(text: str) -> float | None:
    """Utilisation from `iostat -n 0 -c 2 -w 1`: its last row's idle (the first is since boot)."""
    rows = [line.split() for line in text.splitlines()]
    head = next((r for r in rows if "id" in r), None)
    nums = [r for r in rows if r and re.fullmatch(r"[\d.]+", r[0])]
    return round(1 - float(nums[-1][head.index("id")]) / 100, 3) if head and nums else None


def mac_top(text: str) -> dict:
    m, load = re.search(r"(\d+) threads", text), re.search(r"Load Avg: ([\d.]+)", text)
    return {"machine-threads": int(m[1]) if m else None, "cpu-load": float(load[1]) if load else None}


# ---- Linux

def proc_cpu(a: str, b: str) -> float | None:
    """Utilisation between two reads of /proc/stat (idle and iowait are idle)."""
    def busy(t: str) -> tuple[int, int]:
        v = [int(x) for x in t.splitlines()[0].split()[1:9]]
        return sum(v), v[3] + v[4]
    (t0, i0), (t1, i1) = busy(a), busy(b)
    return round(1 - (i1 - i0) / (t1 - t0), 3) if t1 > t0 else None


def linux_memory(meminfo: str, psi: str = "") -> dict:
    kb = {k: int(v) for k, v in re.findall(r"^(\w+):\s+(\d+)", meminfo, re.M)}
    m = re.search(r"some avg10=([\d.]+)", psi or "")
    total = kb["MemTotal"] * 1024
    return memory(total, total - kb["MemAvailable"] * 1024, round(float(m[1]) / 100, 3) if m else None)


def loadavg(text: str) -> dict:
    f = text.split()
    return {"cpu-load": float(f[0]), "machine-threads": int(f[3].split("/")[1])}


def read(p: str) -> str:
    try:
        return Path(p).read_text()
    except OSError:
        return ""


def host() -> dict:
    if sys.platform == "darwin":
        out = mac_top(sh("top", "-l", "1", "-n", "0"))
        out["cpu-utilisation"] = iostat_cpu(sh("iostat", "-n", "0", "-c", "2", "-w", "1"))
        vm = sh("vm_stat")
        if vm:
            out |= mac_memory(sh("sysctl", "-n", "hw.memsize"), vm, sh("sysctl", "-n", "kern.memorystatus_level"))
        return out
    a = read("/proc/stat")
    time.sleep(1)
    out = loadavg(read("/proc/loadavg")) | {"cpu-utilisation": proc_cpu(a, read("/proc/stat")) if a else None}
    return out | linux_memory(read("/proc/meminfo"), read("/proc/pressure/memory"))


# ---- Docker

def docker_stats(text: str) -> dict:
    """`docker stats --no-stream --format '{{json .}}'`: each container's CPU (cores) and memory (GB)."""
    out = {}
    for line in text.splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        out[d.get("Name", "")] = {"cpu": round(float(str(d.get("CPUPerc", "0")).rstrip("%") or 0) / 100, 3),
                                  "memory": round(size_gb(str(d.get("MemUsage", "")).split("/")[0]), 3)}
    return out


def docker_df(text: str) -> float:
    return round(sum(size_gb(json.loads(x).get("Size", "")) for x in text.splitlines() if x.startswith("{")), 2)


def docker(info: str, stats: str) -> dict:
    """`docker info` (`{{.NCPU}} {{.MemTotal}}`) and the containers: the VM's limits and use, the factory's own."""
    f = info.split()
    if len(f) < 2:
        return {}
    cpus, mem, every = int(f[0]), int(f[1]) / GB, docker_stats(stats)
    mine = {n: c for n, c in every.items() if n.startswith(PREFIX)}
    used_cpu, used_mem = sum(c["cpu"] for c in every.values()), sum(c["memory"] for c in every.values())
    return {"vm-cpus": cpus, "vm-memory": round(mem, 2), "vm-cpu-used": round(used_cpu, 3),
            "vm-memory-used": round(used_mem, 3), "vm-cpu-utilisation": round(used_cpu / cpus, 3),
            "vm-memory-utilisation": round(used_mem / mem, 3), "containers": mine,
            "factory-cpu": round(sum(c["cpu"] for c in mine.values()), 3),
            "factory-memory": round(sum(c["memory"] for c in mine.values()), 3)}


VM = "com.apple.Virtualization.VirtualMachine"


def open_files(lsof: str) -> int | None:
    """`lsof -n -P -F f -p <pids>`: the most files any one of those processes holds open (its limit is per process);
    None when no process is listed."""
    counts = []
    for x in lsof.splitlines():
        if x.startswith("p"):
            counts.append(0)
        elif x.startswith("f") and counts:
            counts[-1] += 1
    return max(counts) if counts else None


def vm_open_files() -> int | None:
    """The open files of Docker Desktop's VM (macOS only: none elsewhere, nor while no VM runs): its file sharing keeps
    one for every file a container read through a bind mount (dev/records/suites-copy-their-checkout-into-the-container.md)."""
    pids = sh("pgrep", "-f", VM).split() if sys.platform == "darwin" else []
    return open_files(sh("lsof", "-n", "-P", "-F", "f", "-p", ",".join(pids), timeout=90)) if pids else None


def disk_free(cfg: dict) -> float | None:
    """The least free on the volumes holding <live> and Docker's data."""
    where = [fac.path(cfg, "live"), Path.home() / "Library/Containers/com.docker.docker/Data", Path("/var/lib/docker")]
    free = [shutil.disk_usage(p).free / GB for p in where if p.exists()]
    return round(min(free), 2) if free else None


# ---- the snapshot

SLOW_READINGS = ("docker-disk", "sessions-disk", "installs-disk", "factory-disk", "vm-open-files",
                 "sessions-removed-early")


def take(cfg: dict) -> dict:
    s = {"cpus": os.cpu_count(), **host(), "disk-free": disk_free(cfg)}
    return s | docker(sh("docker", "info", "--format", "{{.NCPU}} {{.MemTotal}}", timeout=15),
                      sh("docker", "stats", "--no-stream", "--format", "{{json .}}", timeout=20))


def take_slow(cfg: dict) -> dict:
    import cleanup
    return {"docker-disk": docker_df(sh("docker", "system", "df", "--format", "{{json .}}", timeout=30)),
            "vm-open-files": vm_open_files(), **cleanup.sizes(cfg)}


def kept(cfg: dict, name: str, fresh: float, measure) -> dict:
    """run/resources/<name>.json, measured again under its lock once older than ``fresh`` (0: only read)."""
    d = fac.run_dir(cfg, "resources")
    p = d / f"{name}.json"
    with open(d / f"{name}.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX if fresh else fcntl.LOCK_SH)
        try:
            try:
                got = json.loads(p.read_text())
            except (OSError, ValueError):
                got = {}
            if fresh and time.time() - float(got.get("at") or 0) > fresh:
                got = {"at": time.time(), **measure(cfg)}
                p.with_suffix(".new").write_text(json.dumps(got))
                p.with_suffix(".new").replace(p)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    return got


def snapshot(cfg: dict, slow: bool = False) -> dict:
    """The host's and Docker's readings (at most 25 s old), and the slow ones as last measured (10 minutes, when
    ``slow``: under a lock of their own, so a long du never holds the fast readings)."""
    return kept(cfg, "slow", SLOW if slow else 0, take_slow) | kept(cfg, "snapshot", FAST, take)


# ---- per session, and the headroom

def ledger(cfg: dict) -> Path:
    return fac.run_dir(cfg, "resources") / "sessions.jsonl"


@contextmanager
def sampled(cfg: dict, name: str, role: str, every: float = 30.0):
    """One container's CPU and memory, from the snapshot, while the body runs: its peak and mean in the dict yielded
    (empty when no sample was taken), and in the ledger."""
    use: dict = {}
    xs: list[dict] = []
    done, began = threading.Event(), time.time()

    def look():
        while not done.wait(every):
            try:
                c = snapshot(cfg).get("containers", {}).get(name)
            except Exception:  # noqa: BLE001 - a sample missed is not the session's failure
                c = None
            if c:
                xs.append(c)
    threading.Thread(target=look, daemon=True).start()
    try:
        yield use
    finally:
        done.set()
        if xs:
            use.update(role=role, container=name, samples=len(xs), seconds=round(time.time() - began),
                       **{f"{k}_{f.__name__}": round(f([x[k] for x in xs]), 3) for k in ("cpu", "memory")
                          for f in (max, statistics.mean)})
            with ledger(cfg).open("a") as out:
                out.write(json.dumps({"at": time.time(), **use}) + "\n")


def per_session(cfg: dict, rows: list[dict] | None = None) -> tuple[float, float]:
    """(CPUs, GB) one session takes: the median peak of the last 20 sessions plus that of the last 20 suites, each
    once three are measured, else [resources] session_* and suite_*. With machine-wide suite slots ([suites] slot) a
    session is charged its own cost alone: the slots cap the suites, and the load reading includes those running."""
    r, slots = cfg.get("resources", {}), bool(cfg.get("suites", {}).get("slot"))
    if rows is None:
        rows = [json.loads(x) for x in read(str(ledger(cfg))).splitlines() if x.strip()]

    def median(suite: bool, key: str, default: float) -> float:
        xs = [x[f"{key}_max"] for x in rows if (x.get("role") == "suite") == suite and f"{key}_max" in x][-20:]
        return statistics.median(xs) if len(xs) >= 3 else float(default)

    def suite(key: str, default: float) -> float:
        return 0.0 if slots else median(True, key, default)
    return (median(False, "cpu", r.get("session_cpus", 0.5)) + suite("cpu", r.get("suite_cpus", 4)),
            median(False, "memory", r.get("session_memory_gb", 1)) + suite("memory", r.get("suite_memory_gb", 4)))


def setpoints() -> dict:
    text = read(str(fac.HERE / "model" / "resources.yaml"))
    out = {}
    for k, goal in GOALS.items():
        m = re.search(rf"^  {goal}:\s*$.*?^\s*hold:\s*\"[<>]=\s*([\d.]+)\"", text, re.M | re.S)
        if not m:
            raise RuntimeError(f"no {goal} goal with a hold in dev/model/resources.yaml")
        out[k] = float(m[1])
    return out


def headroom(s: dict, sp: dict, each: tuple[float, float]) -> int:
    """How many more sessions fit (0 when nothing is known)."""
    if (s.get("disk-free") is not None and s["disk-free"] < sp["disk"]) or (s.get("machine-threads") or 0) > sp["threads"]:
        return 0
    cpu, mem = each
    fits = []
    if s.get("cpus") and s.get("cpu-utilisation") is not None:
        fits.append(s["cpus"] * (sp["cpu"] - s["cpu-utilisation"]) / cpu)
    if s.get("memory-total"):
        fits.append((s["memory-total"] * sp["memory"] - s["memory-used"]) / mem)
    if s.get("vm-cpus"):
        fits += [(s["vm-cpus"] * sp["cpu"] - s["vm-cpu-used"]) / cpu,
                 (s["vm-memory"] * sp["vm-memory"] - s["vm-memory-used"]) / mem]
    return max(0, math.floor(min(fits))) if fits else 0


def room(cfg: dict, role: str) -> int | None:
    """The most of the role's sessions the machine fits now: those running and the headroom (None for the stand-in,
    which takes nothing)."""
    if cfg["ai"]["mode"] == "standin":
        return None
    s = snapshot(cfg)
    running = sum(1 for n in s.get("containers", {}) if n.startswith(f"{PREFIX}{role}-"))
    return running + headroom(s, setpoints(), per_session(cfg))


def reading(cfg: dict, name: str) -> float:
    s = snapshot(cfg, slow=name in SLOW_READINGS)
    v = headroom(s, setpoints(), per_session(cfg)) if name == "session-headroom" else s.get(name)
    if not isinstance(v, (int, float)):
        raise SystemExit(f"resources.py: no {name} reading")
    return v


def line(cfg: dict) -> str:
    s, each = snapshot(cfg, slow=True), per_session(cfg)
    g = lambda k, f="{:g}": "?" if s.get(k) is None else f.format(s[k])  # noqa: E731
    return (f"Resources: CPU {g('cpu-utilisation', '{:.0%}')} (load {g('cpu-load')} on {g('cpus')}), memory "
            f"{g('memory-utilisation', '{:.0%}')} ({g('memory-free', '{:.0f}')} GB free, pressure "
            f"{g('memory-pressure', '{:.0%}')}), disk {g('disk-free', '{:.0f}')} GB free, threads {g('machine-threads')}; "
            f"Docker VM {g('vm-cpus')} CPUs {g('vm-memory', '{:.0f}')} GB: CPU {g('vm-cpu-utilisation', '{:.0%}')} memory "
            f"{g('vm-memory-utilisation', '{:.0%}')}, its disk {g('docker-disk', '{:.0f}')} GB; the factory's "
            f"{len(s.get('containers', {}))} containers {g('factory-cpu', '{:.1f}')} CPUs {g('factory-memory', '{:.1f}')} GB, "
            f"folders {g('sessions-disk', '{:.1f}')} GB sessions ({g('sessions-removed-early')} of finished gaps "
            f"removed early) + {g('installs-disk', '{:.1f}')} GB old installs; "
            f"{headroom(s, setpoints(), each)} more sessions fit (each {each[0]:.1f} CPUs, {each[1]:.1f} GB)")


if __name__ == "__main__":
    c = fac.config()
    print(line(c) if sys.argv[1:] == ["line"] else reading(c, sys.argv[1]))
