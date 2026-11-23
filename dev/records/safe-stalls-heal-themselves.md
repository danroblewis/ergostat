# safe-stalls-heal-themselves: a lease whose process is gone is released, and a stall is said where it is seen

On 2026-11-22 the merge queue stopped for 40 minutes behind a lease whose process had died. The pipeline manager diagnosed it correctly within minutes, in a record nobody was shown, and nothing acted. An engine restart did not end the lease either.

Change:
- The engine releases a lease as soon as the process of the run holding it is gone (the run record's pid and start time), given back **uncounted** when the cause was outside the item (the engine, Docker or a restart). A lease on a remote or detached run is left alone.
- When an engine starts, it ends the leases of runs that no longer exist.
- A run that fails because Docker or the AI service is unreachable is an outage: it pauses and retries, and does not spend the item's attempts or park it.
- The pipeline manager's latest finding is shown on the page's attention list, not only stored in its situation.

Definition of done:
1. A test kills a run's process and its lease is released within one dispatch pass, uncounted, and the queue takes its next batch.
2. A live run's lease is never released, including across a pid reuse.
3. A Docker outage during a run parks nothing, and the items run again when it returns.
