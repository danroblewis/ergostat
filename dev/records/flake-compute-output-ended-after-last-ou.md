# flake-compute-output-ended-after-last-out: test_ended_after_last_out stops failing under load

`tests/test_compute_output.py::test_ended_after_last_out` failed in 4 of the last 40 merge runs and passed alone each time, so the queue excuses it but pays for two reruns and risks a batch. It fails at its assertion near line 210, after `done`: it asserts a run is no longer listed, while other runs from the same test are still listed:

    AssertionError: assert '<run>' not in {'<run>': {'out': 6291456, 'err': 5}, ...}

Find the real cause. If the test reads state that the keeper or node updates asynchronously, wait for that state with the file's own `until`, bounded. If the code can truly keep a finished run listed, fix the code. Do not raise a timeout, skip, retry or quarantine the test.

Definition of done.
1. The cause is named in the record.
2. The test passes 30 times in a row while the machine is loaded with a CPU-bound background job (bounded, with a watchdog, started and stopped by pid).
3. The test still fails if the behavior it guards is broken (show this).

## Where it stopped

Built in round 1 (a test-only change; 0 net lines outside tests and docs).

**The cause (item 1).** The test read stale beats, not a beat written after `done` took effect. The worker sends a `beat`
every 0.1 s from its own thread (`serve.beats`). Each beat's `runs` holds every run `Output` still follows
(`Output.offsets`), and `Output` stops following a run only when the request loop handles `done` (or later, when
`_step` finds the folder gone). The test's `Pipe` keeps every line in a queue in the order it was written. So every beat
written between the killed run's `ended` and the handling of `done` still lists the run (with offsets
`{'out': 0, 'err': 0}`, as in the queue's failure), and those beats wait, unread, ahead of any later one. The test waited
for the folder to go and the keeper to die, then read the next two beats from the queue: the *oldest* unread ones. On a
quiet machine fewer than two stale beats are waiting. Under load the test process reads late, more than two pile up,
and line 210 reads one written before `done`. The code keeps no finished run listed: once `done` is handled, no beat
built after that lists the run. Reproduced exactly by putting `time.sleep(0.5)` before `node.tell("done", ...)` in the
old test (five stale beats): it failed with the queue's message
(`assert '3e02…' not in {'c960…': {'out': 6291456, 'err': 5}, 'e065…': {'out': 0, 'err': 0}, '3e02…': {'out': 0, 'err': 0}}`).

**The fix.** The test now waits for the right beat rather than for longer. It anchors its read on the answer to a request
sent after `done`. The worker handles requests one at a time, in order, so the answer to `ask("done", run=killed)`
("no such run": the folder is gone) is written after `done` was handled. The first beat after that answer may have read
its `runs` just before the answer was written. The second beat after the answer read its `runs` after the first was
sent, so it cannot predate `done`, and that is the one asserted on. No timeout raised, no `until` added (nothing to poll:
the state is already settled when the answer comes), no skip, retry or quarantine. With the same 0.5 s pause, the new
test passes.

**Still fails if broken (item 3).** It was run with the guarded behavior broken in scratch edits, all reverted:
- `Output`'s `done` handler not popping the run, *and* `_step` not dropping a run whose folder is gone: fails at line
  211 with the killed run listed with `{'out': 0, 'err': 0}`. (Breaking only the pop in `done` passes, because `_step`
  also stops following a removed folder within one look. Either is enough to unlist the run.)
- `sampler.Readings.latest` listing ended runs too: fails at line 211 with the killed run listed with `resources`.

**Loaded runs (item 2): not run here.** CLAUDE.md says a factory session neither runs a repeated or loaded measurement
nor works around that. The factory runs it on the branch head, e.g.
`python3 dev/bin/manage.py measure-runs gap/flake-compute-output-ended-after-last-out --runs 30 --load 4 --tests "tests/test_compute_output.py::test_ended_after_last_out"`.
What was run here: the test alone, the whole of `tests/test_compute_output.py` (6 passed), ruff, and the reproductions above.

## Where it stopped

Parked by the factory (review/flake-compute-output-ended-after-last-ou-1, 2026-11-23 08:14).

Done: the cause is named and correct (the test asserted on stale beats still queued in the test's pipe, built before done took effect; the code keeps no finished run listed). The test-only fix anchors on the answer to a request sent after done and asserts on the second beat after it, which must have been built after the run was dropped (checked against output.py and serve.py). Breaking the guarded behaviour was shown to fail the test (item 3). Left: done item 2, 30 consecutive passes under CPU load, which a factory session may not run (CLAUDE.md:80-85).
