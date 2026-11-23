# switch-without-draining: a version switch leaves running agents alone

depends-on: [engine-adopts-runs-from-their-journals]

Problem. `dev/bin/live.py switch` drains: it waits for runs to end or stops them, which delays every upgrade and throws away agents' work.

Change.
- Turn on `[runs] outlive_engine` for the factory.
- A switch stops the engine, swaps the version and starts it; runs under way carry on under the version they started with and are adopted by the new engine. Remove the drain wait, `drain_minutes` and `quiet_runs` where nothing needs them any more.
- A journal or run record written by the previous version must be readable by the next: state the format's version in the journal and refuse, visibly, one it cannot read.
- A switch that is reverted adopts runs the same way.

Definition of done.
1. A test switch with runs under way: none is stopped, none loses an attempt, all finish and are recorded.
2. A reverted switch: the same.
3. A journal of an unknown format version is refused and named, and its run's lease is released uncounted.
4. The upgrade documentation says what a switch does to running work.

Files: dev/bin/live.py, dev/bin/drain.py, tests for them, docs/SPEC.md.
