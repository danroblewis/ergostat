# event-log-indexes-what-it-is-asked: no routine event-log question reads the whole log

The event log's sealed segments index events by item and by type, but not by what caused them. `Events.caused_by(run)` therefore decompresses and parses every segment, on a log of about a million events, and its cost grows with the record. The lease dispatcher calls it for each overdue lease, so one stall with many overdue leases kept the single dispatcher thread scanning and stopped all new work. About a dozen other callers use the same query.

Change.
1. Index `causedby` in each segment and in the live head, so `caused_by` reads only the matching rows. Existing segments must work without being rewritten, for example through an index built once beside them.
2. List every query in `segments.py` that still falls through to a full scan (a `test=` predicate, `item_test`, or no selective filter). Index it or bound it, and name any left unbounded with the reason.
3. The dispatcher must not let reading one lease's activity delay taking work for other blocks.
4. Add a query-cost check: a test that counts segments or rows read, so a new full scan on a routine path fails a test instead of showing up as a slowdown in production.

Keep the JSONL-and-segments record as the source of truth. Do not replace the storage engine in this gap. If the measured query mix shows the format cannot serve it, write that up with numbers as a proposal.

Definition of done.
1. `caused_by` on a synthetic log of 1,000,000 events reads only segments holding matches, and its time does not grow with unrelated events.
2. Answers are identical to the old scan, including events still in the head and across a segment seal.
3. Old segments with no index still answer correctly.
4. A test shows many overdue leases do not delay a take.
5. Do not measure the live instance in the session.
