# why-is-it-not-done: one plain answer to "why isn't this done?" for any item

The owner, 2026-11-22: "figure out what is holding up processes, figure out why certain things have not been done yet." This must work on any model, from what the model declares, with nothing about this factory in core code.

Change: `ergostat why ITEM`, `GET /api/why?item=`, the same through MCP, and a short "Why isn't this done?" block at the top of an unfinished item's page. The answer reads the item index and the model, and states:

- **Now:** its state, for how long, and whether that is unusual for its kind (against the kind's time-in-state).
- **The cause**, followed to its end rather than one hop: what it waits on, what that waits on, down to the root. A root is one of: unfinished work (an item), a person (an inbox item, who, and since when), a full pool, a gate or budget refusing runs, a dead or stale lease, a block that is failing or not running, a closed goal or intake, a parked or dead dependency, or nothing taking this state at all.
- **Next step and owner:** who or what must act, and the exact action or command.
- **Evidence:** the events or readings each claim comes from, with links. When the record cannot tell, it says so and says what is missing. It never guesses.
- A one-paragraph **plain summary** fit to paste to a stakeholder, and `--json`.

Definition of done:
1. Fixture tests for each kind of root above give the right root, owner and next step.
2. Replays of this factory's real stalls of 2026-11-22 as fixtures: a dependency chain; a queue held by a lease whose process died; every build refused by the budget guard; a gap waiting on a parked gap. Each names the true cause.
3. A cycle, a missing dependency or an unreadable field gives a clear answer rather than an error.
4. It answers in under 100 ms on a factory-size record, with no event-log scan for an item's current state.
