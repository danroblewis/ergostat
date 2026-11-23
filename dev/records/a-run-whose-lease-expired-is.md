## Entry

section: Runtime, scale and latency

- **A run whose lease expired is killed** (done, 5fa37de, `leasekill-only`; the owner decided 2026-11-18; SPEC §9.5
  *Fencing*): TERM to its process tree, KILL after a grace, `ergostat.run.killed`; its cost recorded, its item retried.
