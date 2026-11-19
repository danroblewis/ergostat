"""Reading ``daemons:`` and a block's or a sensor's ``daemon:`` (SPEC §9.7) into the spec, every mistake said with where
it was written. Called by the spec compiler with itself, for its ``named``, ``keys``, ``duration`` and ``err``."""

from __future__ import annotations

from ..spec.ir import Daemon

KEYS = {"run", "concurrency", "heartbeat", "restart", "stdin-timeout", "description"}
RESTART = {"max", "within", "backoff"}


def one(c, m, name: str, what: str) -> Daemon | None:
    c.keys(m, KEYS, what)
    if not m.get("run"):
        c.err(f"{what}: run: the command that starts it (it reads JSON lines on its standard input, SPEC §9.7)",
              m.where, "missing-key")
        return None
    n = m.get("concurrency", 10)
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        c.err(f"{what}.concurrency: a whole number, 1 or more (the most runs it holds at once)", m.at("concurrency"),
              "bad-number")
        n = 1
    r = m.get("restart") or {}
    if not isinstance(r, dict):
        c.err(f"{what}.restart: a map: max, within, backoff", m.at("restart"), "not-a-map")
        r = {}
    else:
        c.keys(r, RESTART, f"{what}.restart")
    most = r.get("max", 5)
    if isinstance(most, bool) or not isinstance(most, int) or most < 0:
        c.err(f"{what}.restart.max: a whole number (restarts allowed within: before it is given up)", r.at("max"),
              "bad-number")
        most = 5
    back = r.get("backoff") or ["1s", "2m"]
    if not isinstance(back, list) or len(back) != 2:
        c.err(f"{what}.restart.backoff: [first, most]: the first restart's wait, doubled each time up to the most",
              r.at("backoff"), "bad-duration")
        back = ["1s", "2m"]
    from ..durations import DurationError, parse_duration
    try:
        backoff = tuple(parse_duration(x, f"{what}.restart.backoff") for x in back)
    except DurationError as e:
        c.err(f"{e} (like 1s, 2m)", r.at("backoff"), "bad-duration")
        backoff = (1.0, 120.0)
    return Daemon(name, str(m["run"]), n, c.duration(m, "heartbeat", what), most,
                  c.duration(r, "within", f"{what}.restart", 600.0) if r else 600.0, backoff,
                  c.duration(m, "stdin-timeout", what, 10.0), m.where)


def section(c, spec) -> None:
    """The top-level ``daemons:``, then each block's and sensor's ``daemon:`` (a map: its own, named for it; a name:
    the top-level one), resolved to a name in ``spec.daemons``."""
    for name, m, what in c.named("daemons"):
        if (d := one(c, m, name, what)) is not None:
            spec.daemons[name] = d
    top = ", ".join(sorted(spec.daemons)) or "none"
    users = [(f"block.{b.name}", b, b.params.get("daemon"), f"block {b.name}") for b in spec.blocks.values()
             if b.params.get("daemon") is not None]
    users += [(f"sensor.{s.of.name}.{s.name}", s, s.daemon, f"{s.of.kind} {s.of.name} sensor {s.name}")
              for s in spec.sensors() if s.daemon is not None or s.push]
    for own, x, raw, what in users:
        name = None
        if isinstance(raw, dict):
            if (d := one(c, raw, own, f"{what}.daemon")) is not None:
                spec.daemons[own] = d
                name = own
        elif isinstance(raw, str) and raw in spec.daemons:
            name = raw
        elif raw is not None:
            c.err(f"{what}.daemon: a map (run:, concurrency:, heartbeat:, restart:, stdin-timeout:) or the name of one "
                  f"under daemons: ({top})", x.where, "bad-daemon")
        if own.startswith("block."):
            x.params["daemon"] = name
            if x.type != "program" or x.params.get("run"):
                c.err(f"{what}: daemon: is a program block's, instead of run:", x.where, "bad-daemon")
        else:
            x.daemon = name
            if x.push and raw is None:
                c.err(f"{what}.push: a daemon's sensor (daemon:, and push: true when it sends readings itself)",
                      x.where, "bad-daemon")
