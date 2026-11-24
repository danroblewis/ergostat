# daemons-reconnect-after-the-engine: a daemon keeps running through an engine restart and picks its messages back up

depends-on: [engine-adopts-runs-from-their-journals]

Owner, 2026-11-23: "for daemons, the ones that receive messages from ergostat, that may be different, but even those could be separated."

Problem. A daemon (SPEC 9.7) is a child of the engine and receives its messages over a connection to it, so it stops with the engine.

Change.
- A daemon runs under a keeper as runs do, with its output in a journal.
- Messages to it are delivered from a durable position: while no engine is up it simply receives nothing and keeps doing what it holds. A new engine reconnects and delivers from where it left off, at least once, with an id the daemon can use to drop a repeat.
- A daemon declared to stop with the engine keeps that behaviour.

Definition of done.
1. Kill the engine with a daemon mid-item: the daemon finishes the item, and its result is recorded after restart.
2. A message sent before the kill and not acknowledged is delivered again with the same id; none is lost.
3. A daemon that died during the outage is restarted by the new engine.
4. Existing daemon tests pass.

Files: ergostat's daemon modules, tests/test_daemons_outlive_engine.py (new), docs/SPEC.md.
