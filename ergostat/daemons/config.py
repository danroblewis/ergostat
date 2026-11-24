"""Reading ``daemons:`` and a block's or a sensor's ``daemon:`` (SPEC §9.7) into the spec, every mistake said with where
it was written. Called by the spec compiler with itself, for its ``named``, ``keys``, ``duration`` and ``err``."""

from __future__ import annotations

from ..spec.ir import Daemon

KEYS = {"run", "concurrency", "heartbeat", "restart", "stdin-timeout", "description", "warm", "recycle",
        "outlive-engine"}
RESTART = {"max", "within", "backoff"}
WARM_MOST = 32                 # a warm daemon's processes, at most (two engine threads each)
STORE = "victoriametrics"      # the daemon of storage: measurements: run: (the metrics store ergostat supervises)
WARM_ALL = 64                 # every warm daemon's processes together, at most (draining ones counted while running)


def whole(c, m, key: str, least: int, default: int, what: str, says: str) -> int:
    v = m.get(key, default)
    if isinstance(v, bool) or not isinstance(v, int) or v < least:
        c.err(f"{what}.{key}: a whole number, {least} or more ({says})", m.at(key), "bad-number")
        return default
    return v


def one(c, m, name: str, what: str, outlive: bool = False) -> Daemon | None:
    c.keys(m, KEYS, what)
    if not m.get("run"):
        c.err(f"{what}: run: the command that starts it (it reads JSON lines on its standard input, SPEC §9.7)",
              m.where, "missing-key")
        return None
    r = m.get("restart") or {}
    if not isinstance(r, dict):
        c.err(f"{what}.restart: a map: max, within, backoff", m.at("restart"), "not-a-map")
        r = {}
    c.keys(r, RESTART, f"{what}.restart")
    back = r.get("backoff") or ["1s", "2m"]
    from ..durations import DurationError, parse_duration
    try:
        backoff = tuple(parse_duration(x, f"{what}.restart.backoff") for x in back) if isinstance(back, list) else ()
    except DurationError:
        backoff = ()
    if len(backoff) != 2:
        c.err(f"{what}.restart.backoff: [first, most], like [1s, 2m]: the first restart's wait, doubled each time up to "
              f"the most", r.at("backoff"), "bad-duration")
        backoff = (1.0, 120.0)
    warm = m.get("warm", False)
    if not isinstance(warm, bool) or ("recycle" in m and not warm):
        c.err(f"{what}.warm: true or false (true: the program keeps no state between runs; recycle: only with it)",
              m.at("warm") if "warm" in m else m.at("recycle"), "bad-daemon")
        warm = False
    if warm is True and isinstance(m.get("concurrency"), int) and m["concurrency"] > WARM_MOST:
        c.err(f"{what}.concurrency: at most {WARM_MOST} for a warm daemon (a process each, two engine threads each)",
              m.at("concurrency"), "bad-number")
        warm = False
    kept = m.get("outlive-engine", outlive and not warm)    # (as runs: outlive_engine says, unless it says itself)
    if not isinstance(kept, bool) or kept and warm:
        c.err(f"{what}.outlive-engine: true or false (true: kept by a keeper, going on through an engine restart; "
              f"never a warm daemon's)", m.at("outlive-engine"), "bad-daemon")
        kept = False
    return Daemon(name, str(m["run"]), whole(c, m, "concurrency", 1, 10, what, "the most runs it holds at once"),
                  c.duration(m, "heartbeat", what), whole(c, r, "max", 0, 5, f"{what}.restart", "restarts allowed within:"),
                  c.duration(r, "within", f"{what}.restart", 600.0) if r else 600.0, backoff,
                  c.duration(m, "stdin-timeout", what, 10.0), warm is True,
                  whole(c, m, "recycle", 1, 1000, what, "the most runs one warm process serves"), m.where, kept)


def section(c, spec) -> None:
    """The top-level ``daemons:``, then each block's and sensor's ``daemon:`` (a map: its own, named for it; a name:
    the top-level one), resolved to a name in ``spec.daemons``."""
    for name, m, what in c.named("daemons"):
        if (d := one(c, m, name, what, spec.outlive_engine)) is not None:
            spec.daemons[name] = d
    if run := getattr(getattr(spec, "storage", None), "run", None):
        if STORE in spec.daemons:
            c.err(f"daemons.{STORE}: the name of the daemon storage: measurements: run: makes; call this one another",
                  spec.daemons[STORE].where, "bad-daemon")
        else:              # (it serves no run and no reading: it is started, kept and stopped as every daemon is)
            spec.daemons[STORE] = Daemon(STORE, run, concurrency=1)
    top =", ".join(sorted(spec.daemons)) or "none"
    users = [(f"block.{b.name}", b, b.params.get("daemon"), f"block {b.name}") for b in spec.blocks.values()
             if b.params.get("daemon") is not None]
    users += [(f"sensor.{s.of.name}.{s.name}", s, s.daemon, f"{s.of.kind} {s.of.name} sensor {s.name}")
              for s in spec.sensors() if s.daemon is not None or s.push]
    for own, x, raw, what in users:
        name = None
        if isinstance(raw, dict):
            if (d := one(c, raw, own, f"{what}.daemon", spec.outlive_engine)) is not None:
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
            if name and spec.daemons[name].warm:
                c.err(f"{what}.daemon: a warm daemon (warm: true) serves blocks' runs only, not readings", x.where,
                      "bad-daemon")
            if x.push and raw is None:
                c.err(f"{what}.push: a daemon's sensor (daemon:, and push: true when it sends readings itself)",
                      x.where, "bad-daemon")
    if (n := sum(d.concurrency for d in spec.daemons.values() if d.warm)) > WARM_ALL:
        c.err(f"daemons: {n} warm processes in all; at most {WARM_ALL} (lower their concurrency)", None, "bad-number")
