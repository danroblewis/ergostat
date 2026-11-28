"""``ergostat.daemon``, the built-in projection of daemons (SPEC §9.7, *A daemon is an object*): one object per daemon,
``ergostat.daemon/<name>`` (a warm daemon's processes, NAME#i, are one daemon: each event says which ``process``),
folded from what its supervisor records on change only:

- ``ergostat.daemon.started``: running, with its pid, the blocks and sensors it serves, its log (while kept);
- ``ergostat.daemon.restarted``: restarting, with why (exited, silent past its heartbeat, an alarm), the back-off;
- ``ergostat.daemon.failed``: given up after too many restarts (an intervention, its alarm);
- ``ergostat.daemon.stopped``: drained (nothing uses it now, its definition changed) or ergostat stopping.

``given-up`` is the state of ``ergostat.daemon.failed``: the daemon a supervisor no longer restarts. A daemon that
merely failed and is being restarted is ``restarting``. Its live state between events (its last line's time, what it
holds in flight, its CPU) stays in ``daemons.json``, never an event per line."""

from __future__ import annotations

DAEMON = "ergostat.daemon"
STATES = ["running", "restarting", "given-up", "stopped"]
ON = {f"{DAEMON}.started": "running", f"{DAEMON}.restarted": "restarting", f"{DAEMON}.failed": "given-up",
      f"{DAEMON}.stopped": "stopped"}


def kind():
    from ..spec.ir import ItemKind
    return ItemKind(DAEMON, f"{DAEMON}/*", list(STATES), dict(ON),
                    ["pid", "restarts", "serves", "alarm", "why", "log"], {}, None,
                    "one daemon: running, restarting, given up or stopped; its pid, restarts, the blocks and sensors "
                    "it serves, its alarm and why, and its log while kept; its history its starts, restarts, failures "
                    "and stops (built in, SPEC §9.7)", sealed=True)


def base_of(name: str) -> str:
    """A warm daemon's process (NAME#i): its daemon, NAME."""
    return name.rpartition("#")[0] or name


def item_of(name: str) -> str:
    return f"{DAEMON}/{base_of(name)}"


def link(name: str) -> str:
    return f"/{item_of(name)}"
