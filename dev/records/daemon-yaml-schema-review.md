## Entry

section: Runtime, scale and latency

- **Daemon YAML schema review** (open; owner, 2026-11-19): the functionality landed (`daemons`, `daemons2`; how to
  use and write daemons: `docs/DAEMONS.md`, the skill's `daemons.md`), but the owner is not sure the YAML is the
  best yet, and it may change. The options, what each would cost and a recommendation for each are in
  [docs/proposals/daemon-yaml.md](proposals/daemon-yaml.md) (`docs/proposals/daemon-yaml.md`); the gap waits for the
  owner's choice. Alternatives worth considering:
  - *a modifier instead of a kind*: `run: python3 probe.py` plus `keep: true` (or `mode: daemon`), so moving a
    sensor over is one word and the command stays where it was, rather than `daemon: {run: ...}` as a seventh
    sensor kind;
  - *per-sensor arguments*: today a shared daemon works out what to read from the sensor's name (`orders.main` is
    the `orders` queue), so names carry configuration; a sensor's own `with: {queue: orders}`, sent in its read
    line, would free the names;
  - *where shared daemons are declared*: a top-level `daemons:` beside `agents:` (SPEC §10, the machine several
    blocks share), or a daemon as an agent's process (`agents: {svc: {kind: program, daemon: {...}}}`), which
    would show it on its rung like every other agent;
  - *the names of inline daemons* (`sensor.STOCK.SENSOR`, `block.NAME`), derived and dotted, used by
    `ergostat block NAME --restart` and in logs;
  - *push*: `push: true` beside `daemon:` on the sensor, or said once by the daemon (it pushes for every sensor
    that names it);
  - *the knobs*: `concurrency` beside the block's `pool` (two limits on one thing); `restart.backoff` as a
    two-item list against `backoff:` and `max-backoff:`; `stdin-timeout`'s name; a heartbeat on by default for
    block daemons;
  - *the word*: "daemon" is Unix jargon; `runner`, `server` or `keep-alive` may read better to the owner's users.
  Whatever changes, the protocol (SPEC §9.7) need not: these are only how the YAML says which process and how it
  is supervised. The docs' examples are run by `tests/test_daemon_docs.py`, so a schema change shows every place
  to rewrite. Found by the review: a non-warm daemon's `concurrency` has a floor of 1 and no maximum
  (`ergostat/daemons/config.py:52`), and it multiplies engine threads, one per run the daemon holds
  (`ergostat/leases/dispatch.py:223`), bounded only by its blocks' `pool`, which has no maximum either
  (`ergostat/leases/compile.py:85-90`); only warm daemons are capped (32 each, 64 in all). Lesson-4: recorded, not
  yet fixed.
