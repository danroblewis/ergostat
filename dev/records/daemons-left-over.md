## Entry

section: Done recently

- **Daemons, left over** (done on `factory/daemons-left-over`; SPEC §6 and §9.7,
  `docs/roadmap/overnight/daemons-left-over.md`): a daemon's lines that arrive together are taken together, per run,
  up to 500 at once, in the order printed (`ergostat/daemons/lines.py`), and a line over 1 MiB is dropped; a sensor
  daemon's observations (`{"event": ..., "item": ..., "sensor": S}`, or a relayed `{"message": ...}`) are checked and
  recorded as a `run:` sensor's are, from that sensor, at most 50 a second, the drops counted and said once
  (`ergostat/daemons/observe.py`), and one for a sensor the daemon does not serve is dropped; a new daemon's CPU is
  sampled about 1 s after it starts, then at doubling gaps up to every 30 s, never two samples within 1 s
  (`ergostat/costs/sampler.py`).
