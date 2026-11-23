"""The limits on what an untrusted library's templates make (SPEC §2a, *Untrusted libraries*): its sensors' and blocks'
schedules and its runs at once, checked when the model is compiled (``check``) and again when a run starts (``room``)
and when the clock paces it (``pace``). Constants, not config: nothing here is read from a file.

A part is untrusted when it was made by an instance (its ``where`` a ``Via``) whose entry in ``uses`` does not say
``untrusted: False`` exactly: an instance that is gone, or an entry without the flag, counts as untrusted."""

from __future__ import annotations

from ..cron import Cron, CronError
from .expand import Via

UNTRUSTED_EVERY = 300.0       # seconds: the shortest period of an untrusted sensor, block or judge
UNTRUSTED_POOL = 2            # the most runs at once of one untrusted block that takes items
UNTRUSTED_RUNS = 4            # the most runs at once of every untrusted block of the model together
UNTRUSTED_ATTEMPTS = 5        # the most attempts an untrusted block's lease allows an item
STARTED = ("program", "ai", "judge")
CODE = "untrusted-limit"


def untrusted_part(where, uses) -> bool:
    if not isinstance(where, Via):
        return False                                    # the model's own (or a remote's): not a library's
    u = (uses or {}).get(where.instance)
    return not (isinstance(u, dict) and u.get("untrusted") is False)


def default_every(uses, where, default: float) -> float:
    """A sensor's period when none is written: the floor for an untrusted one."""
    return UNTRUSTED_EVERY if untrusted_part(where, uses) else default


def _hourly(cron: str | None) -> bool:
    try:
        return cron is None or len(Cron(cron).sets[0]) == 1
    except CronError:
        return False


def _timing(c, what: str, every, cron, where) -> None:
    if every is not None and every < UNTRUSTED_EVERY:
        c.err(f"{what}.every: at least {UNTRUSTED_EVERY:g}s ({UNTRUSTED_EVERY / 60:g}m) for a part an untrusted library "
              f"made", where, CODE)
    if not _hourly(cron):
        c.err(f"{what}.cron: one minute of the hour at most (like '7 * * * *') for a part an untrusted library made",
              where, CODE)


def check(c, spec) -> None:
    """After ``leases.check``: each untrusted part marked, and every limit it passes an ``untrusted-limit`` error."""
    from ..leases.terms import terms
    for s in spec.sensors():
        s.untrusted = untrusted_part(s.where, spec.uses)
        if not s.untrusted:
            continue
        what = f"{s.of.kind} {s.of.name} sensor {s.name}"
        _timing(c, what, s.every, s.cron, s.where)
        if s.daemon is not None or s.push:
            c.err(f"{what}.daemon: an untrusted library's sensor is read by a command, run in ergostat.sandbox, never "
                  f"a daemon, which nothing sandboxes", s.where, "library-unsandboxed")
    total, over = 0, False
    for b in spec.blocks.values():
        b.untrusted = untrusted_part(b.where, spec.uses)
        if not b.untrusted or b.type not in STARTED:
            continue
        what, about = f"block {b.name}", f"block.{b.name}"
        if b.type == "judge" and b.every is None:
            b.every = UNTRUSTED_EVERY
        _timing(c, what, b.every, b.cron, b.where)
        if b.on is not None:
            c.err(f"{what}.on: an untrusted library's block is never started by an event", b.where, CODE, about)
        if b.type != "judge" and not (b.every or b.cron or b.takes):
            c.err(f"{what}: an untrusted library's block needs every:, cron: or takes: (else it runs on every reading of "
                  f"its inputs)", b.where, CODE, about)
        if b.pool > UNTRUSTED_POOL:
            c.err(f"{what}.pool: at most {UNTRUSTED_POOL} for an untrusted library's block", b.where, CODE, about)
        if b.type != "judge" and (b.takes or b.lease.attempts is not None):
            n = terms(spec, b)["attempts"]
            if n > UNTRUSTED_ATTEMPTS:
                c.err(f"{what}: its leases allow {n} attempts; at most {UNTRUSTED_ATTEMPTS} for an untrusted library's "
                      f"block (lease: {{attempts: N}}, or the leases: tier it runs on)", b.where, CODE, about)
        total += b.pool if b.takes else 1
        if total > UNTRUSTED_RUNS and not over:
            over = True
            c.err(f"{what}: the untrusted libraries' blocks may run {total} or more at once (a run each, or each pool of "
                  f"a block that takes items); at most {UNTRUSTED_RUNS} together", b.where, CODE, about)


def untrusted_block(spec, name: str, recorded: bool = False) -> bool:
    """A block counts as untrusted when it was when its run began, or the model says it is now, or the model no
    longer has it (removed on a reload, its run still draining)."""
    b = spec.blocks.get(name)
    return recorded or b is None or b.untrusted or untrusted_part(b.where, spec.uses)


def room(engine, b) -> bool:
    """Whether a run of ``b`` may start now: always for a trusted block; for an untrusted one, while fewer than
    ``UNTRUSTED_RUNS`` untrusted runs are in ``engine.running``. Called under ``engine.lock``, with the add."""
    if not untrusted_block(engine.spec, b.name, b.untrusted):
        return True
    flagged = engine.untrusted_runs
    n = sum(1 for k in engine.running if untrusted_block(engine.spec, k.split(" ", 1)[0], k in flagged))
    return n < UNTRUSTED_RUNS


def hold(engine, key: str, b) -> None:
    """A run added to ``engine.running`` (under ``engine.lock``), with whether it is untrusted as it starts: a reload
    that makes the block trusted later does not stop it counting while it drains."""
    engine.untrusted_runs.intersection_update(engine.running)
    engine.running.add(key)
    if untrusted_block(engine.spec, b.name, b.untrusted):
        engine.untrusted_runs.add(key)
    else:
        engine.untrusted_runs.discard(key)


def pace(spec, part, every):
    """The clock's period for a sensor or a block: an untrusted one's never under the floor."""
    if part.untrusted or untrusted_part(part.where, spec.uses):
        return max(every or 0.0, UNTRUSTED_EVERY)
    return every
