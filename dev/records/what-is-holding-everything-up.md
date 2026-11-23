# what-is-holding-everything-up: the system's current constraints, ranked

The owner, 2026-11-22: "figure out what is holding up processes, figure out why certain things have not been done yet." Today's status lists 18 goals off with no sign of which one is holding the rest up.

Change: `ergostat held-up`, `GET /api/held-up`, MCP, and one line at the top of the page. It groups every unfinished item by its root cause (`why-is-it-not-done`) and ranks the roots by what they hold: how many items, how many hours of waiting, and the items that matter most by rank. The first line is the single biggest constraint, in words, with its next step: "The merge queue is held by a dead lease: 60 approved gaps are waiting. Release it with ...". Goals that are off only as a consequence of a root are folded under it. It distinguishes **normal queueing** from a **stall** (something that should be moving and is not), and says "nothing is stuck" only when that is true.

Definition of done:
1. On the fixtures of `why-is-it-not-done`, the true constraint ranks first.
2. The budget-guard stall and the dead-lease stall are each named as the first line, and a healthy busy system reports no stall.
3. A snapshot of 18 off goals with one root shows one root with the rest folded under it.
4. It answers in under 200 ms on a factory-size record.
