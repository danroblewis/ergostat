# runs-keep-going-without-the-engine: a run is not killed when ergostat stops, and writes its lines to its own journal

Owner, 2026-11-23: "when our ergostat server dies, we want the in-progress jobs to work just fine, their only responsibility is to produce the jsonl that ergostat will later consume into its event log, and maybe metrics. there is no reason those should need to have a hard dependency on ergostat."

Problem. A run's stdout is a pipe to the engine (ergostat/runner.py), and the engine kills each run's process group as it stops (SPEC 9.5). So every restart, crash or version switch ends all running agents, and their uncommitted work and tokens are lost. Switches drain for this reason.

Change.
- A block's run starts under a detached keeper in its own session (reuse ergostat/compute/worker/keeper.py rather than writing a second one). The keeper owns the run's process, records its exit, and needs no engine to exist.
- The run's stdout goes to an append-only JSONL journal in the run's folder (`runs/<id>.jsonl`), flushed line by line. The format is the existing run line protocol (SPEC 9.1). The engine reads the journal; it is no longer the other end of a pipe.
- Stopping ergostat, on purpose or by a crash, leaves runs going. `ergostat run --stop --runs` (or a block's `--stop`, a lease expiring, a timeout) is what stops a run. Those keep working through the keeper.
- A call a run makes to the engine (SPEC 9.1, `ERGOSTAT_SOCKET`) while none is up must not fail the run: what only records is written to the journal; what needs an answer waits, as it does now, for longer than an engine restart takes.

This gap does not read journals back after a restart: that is `engine-adopts-runs-from-their-journals`. Until that lands, keep today's behaviour behind one setting, `[runs] outlive_engine` (default false).

Definition of done.
1. With the setting on, a test starts a run, SIGKILLs the engine, and the run carries on to its end, its journal complete and its exit recorded.
2. The same with a clean `ergostat run --stop`.
3. A run's lines in the journal are byte-for-byte what it printed, in order, including a last line with no newline.
4. An explicit stop of a run, a lease expiry and a timeout each still end the whole process group.
5. With the setting off, every existing runner test passes unchanged.

Files: ergostat/runner.py, ergostat/compute/worker/keeper.py, ergostat/spec/runrecord.py, tests/test_runs_outlive_engine.py (new), docs/SPEC.md.
