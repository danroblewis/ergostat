"""A warm process's CPU, read from outside it (SPEC §9.7, *Warm*): for each member of its process group, its own CPU and
that of every descendant it reaped (``RUSAGE_CHILDREN``, which only a process's own ``getrusage`` gives otherwise).
macOS: ``proc_listpgrppids`` and ``proc_pid_rusage`` (libproc); Linux: ``/proc``. Elsewhere nothing is charged.

A run is charged the group's total now less its total at hand-over: a member that ended meanwhile and was reaped
inside the group moved its whole life into its parent, and its part before the run is in the hand-over total. Not
charged: a child that left the group (``setsid``) or was orphaned and reaped outside it, and a member whose usage
cannot be read (EPERM). CPU used after ``done`` falls into the next run's charge."""

from __future__ import annotations

import ctypes
import os

from ..costs.sampler import LINUX, MACOS

_lib = None
_SCALE = 1e-9                  # macOS: rusage times in mach ticks, to seconds


class _Info(ctypes.Structure):  # struct rusage_info_v2
    _fields_ = [("uuid", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in (
        "user", "system", "idle", "interrupts", "pageins", "wired", "resident", "footprint", "start", "exit",
        "child_user", "child_system", "c_idle", "c_interrupts", "c_pageins", "c_elapsed", "read", "written")]


def _libproc():
    global _lib, _SCALE
    if _lib is None:
        class Base(ctypes.Structure):
            _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]
        tb = Base()
        ctypes.CDLL("/usr/lib/libSystem.dylib").mach_timebase_info(ctypes.byref(tb))
        _SCALE = tb.numer / tb.denom / 1e9
        _lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    return _lib


def _members(pgid: int) -> list[int]:
    if MACOS:
        buf = (ctypes.c_int * 256)()
        n = _libproc().proc_listpgrppids(pgid, buf, ctypes.sizeof(buf))
        return [x for x in buf[:max(n, 0)] if x > 0]
    out = []
    for d in os.listdir("/proc"):
        if d.isdigit() and (f := _stat(int(d))) and int(f[2]) == pgid:
            out.append(int(d))
    return out


def _stat(pid: int) -> list[str] | None:
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            raw = f.read().decode(errors="replace")
    except OSError:
        return None
    return raw[raw.rfind(")") + 2:].split()


def _cpu(pid: int) -> float | None:
    """Its own CPU and its reaped descendants', in seconds."""
    if MACOS:
        ri = _Info()
        if _libproc().proc_pid_rusage(pid, 2, ctypes.byref(ri)) != 0:
            return None
        return (ri.user + ri.system + ri.child_user + ri.child_system) * _SCALE
    f = _stat(pid)
    return sum(int(x) for x in f[11:15]) / os.sysconf("SC_CLK_TCK") if f else None


def snapshot(pgid: int) -> dict[int, float]:
    """Each live member of the group, and its CPU so far ({} where this cannot be read)."""
    if not (MACOS or LINUX):
        return {}
    try:
        got = {pid: _cpu(pid) for pid in _members(pgid)}
    except (OSError, AttributeError, ValueError):
        return {}
    return {pid: c for pid, c in got.items() if c is not None}


def _zombie(pid: int) -> bool:
    """Ended, not yet reaped (macOS: libproc gives no BSD info for one; Linux: state Z)."""
    if MACOS:
        return _libproc().proc_pidinfo(pid, 3, 0, ctypes.create_string_buffer(136), 136) <= 0
    f = _stat(pid)
    return bool(f) and f[0] == "Z"


def charge(before: dict[int, float], pgid: int) -> tuple[float, list[int], list[int]]:
    """The CPU the group used since ``before``; the members not there then and still running now (left running, its
    leader never among them); and those that ended but were not reaped (unreaped)."""
    now = snapshot(pgid)
    new = sorted(set(now) - set(before) - {pgid})
    dead = [p for p in new if _zombie(p)]
    return max(0.0, sum(now.values()) - sum(before.values())), [p for p in new if p not in dead], dead
