## Entry

section: Runtime, scale and latency

- **Warm workers instead of a process per item**: superseded by daemons (branch `daemons`, SPEC §9.7,
  `docs/RUNTIME.md`): long-lived processes for blocks and sensors, many items at once, every line tagged with its run
  or request, env per item in its line, supervised (crash, silence, stdin backpressure, restart storms, cancel on a
  lease's expiry, drained on a swap). The `warm` branch stays parked as reference (its definition file,
  `docs/roadmap/overnight/leasekill.md`, says where it stopped); its review's findings were taken as lessons: B4 (a
  `done` for another item) by tagging, B1 (env leaking between items) by env in the line, B3 (a child's CPU never
  charged) by charging no item CPU at all (the daemon's own CPU and memory are sampled and shown); a `warm: true`
  daemon now charges it per item (*Done recently*).
