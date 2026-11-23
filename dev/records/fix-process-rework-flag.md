# fix-process-rework-flag: the Process view counts rework only when an item repeats a step

Confirmed 2026-11-23 in `ergostat/process.py`, `process()` (about line 474). The Process view reports concurrency as rework. Smallest failing case: two items, one doing steps `x, y` and the other `y, x`: nothing is repeated, yet passages are flagged as rework. A synthetic log with no repeated step showed 94 false rework passages.

See `docs/research/2026-11-23-charts/catalog.md`, item B1 and section 7.2.

Change.
- A passage is rework only when the same item returns to a step it has already done. The order in which different items take steps never counts.
- Show the count of returns.
- Where SPEC defines rework in two ways, keep one definition: a repeated step. Update SPEC.

Definition of done.
1. Two items doing `x, y` and `y, x` show no rework.
2. One item doing `x, y, x` shows one return.
3. A generated log with concurrency and no repeated step shows zero rework; the same log with known returns shows exactly those.
4. The existing process tests pass, or a test records a deliberate change.
