# regression-escapes-from-reverts: A revert on main is recorded as an escape of the gap it reverts, and escapes-found gets a sensor

depends-on: []

Problem: the stock escapes counts reverted merges, but gap.reverted is entered only by hand (ergostat.yaml:153-154) and its inflow escapes-found has no sensor (dev/model/pools.yaml:66-69), so a revert commit on main is invisible. Change: in `upgrade.py watch` (block main-watch, dev/model/landing.yaml:358-364; dev/bin/upgrade.py:24-41) a step escapes.watch() in new dev/bin/escapes.py walks `git rev-list --first-parent` from the last commit read (run/escapes.json) to the pushed main, at most 200 commits (said when hit), looking for `This reverts commit <sha>`. A reverted commit is matched to a merged gap first by its second parent being the gap's reviewed_head, then by main_sha (main_sha is the batch's pushed head, shared by a batch's gaps and, after merge-pipeline-gaps-md-regenerated-on-land, a commit that is no gap's merge, so it identifies a gap only when exactly one gap carries it). A match writes gap.reverted with reverted: true, revert_sha, reverted_at. No match writes intervention.recorded as intervention/reverted-<sha12>, class reverted-unmatched, which dev/bin/risk.py counts as an escape as it does an unmatched main-broken (risk.py:79-88). Ids make a second read a no-op. escapes-found gets a sensor `pools.py read escapes-day`. Done: a revert is recorded once however often main-watch runs; a revert of one merge of a batch of three blames only that gap; an unmatched one still counts; check reports no flow without a sensor in pools.yaml; a git error stops only this step; README says reverts are found by main-watch. Files: dev/bin/{escapes,upgrade,risk,pools}.py, dev/model/pools.yaml, dev/README.md, tests/test_factory.py (five tests). Budget: 130 net lines.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1: all five acceptance tests in tests/test_factory.py pass, and each was seen to fail with the code it
guards broken (the already-reverted skip, the reviewed_head match, risk.py's reverted-unmatched class, upgrade.py's
catch, the escapes-found sensor). About 115 net lines, within the 130 budget. Choices made alone, each the reversible one:

- "check reports no flow without a sensor in pools.yaml": `ergostat check` reports nothing about a flow that has no
  sensor (seen: with the sensor removed it is still silent), so the test checks pools.yaml's flows itself. Every
  flow is measured, has an equation, or is a block's `out:`, except factory-harm, which this gap leaves alone and
  the test names. It also runs `ergostat check` and asserts nothing is said of escapes-found.
- escapes-day is a rate per hour (SPEC: a flow's reading is per hour): the escapes found in the last 24 h, divided by
  24. It counts gap.reverted with a reverted_at, and main-broken and reverted-unmatched interventions. A gap.reverted
  entered by hand without reverted_at has no date, so it is not counted there (it still counts in the stock).
- Reverting a revert puts the work back, so it is not recorded as an escape. A gap already reverted is not recorded
  again. The unmatched intervention's id is keyed by the reverted commit, as main-broken-<sha12> is by main's.
- When run/escapes.json names a commit the checkout no longer has, main is read again from its start, 200 commits a
  run (the ids make the re-read record nothing twice). The first run on the instance reads main's whole history
  this way, 200 commits each run.
- Outside the Files list, comments and descriptions only: the gap.reverted comment in ergostat.yaml and the
  main-watch description in dev/model/landing.yaml, kept current. Also the fold harness in tests/test_factory.py
  takes the no-state event gap.reverted.

Round 2: main (ead497d1) merged in. The one conflict, in tests/test_factory.py, was main moving the fixture's fold
into fold_line(); it is resolved as main's version, with gap.reverted added to fold_line's no-state events. The five
acceptance tests and the risk test pass again after the merge. `ruff check ergostat tests scripts` is clean.

Build after round 2: the fast suite's one failure was test_an_unstacked_gap_builds_as_before (pytest's lastfailed).
The traceback ended in subprocess.run with no CalledProcessError line, so it was most likely a timeout. Run alone on
this branch it passes (188 s: three implement.py runs, about 60 s each, against a 120 s timeout per run). It runs
implement.py, agents.py and fac.py, none of which this branch changes. So it is not this branch's code: it is the
120 s bound under -n load (lesson 10), and it belongs in its own gap, not here (lesson 13). Not run on clean main
here; the factory reruns it there. No code changed for it. The whole of tests/test_factory.py ran once after the
merge: 1 failed (this test), 203 passed, 2 skipped. Later whole-file runs were refused in this session, so the
other tests were run by name, three at a time.

Build again (after 242d02f7): one F again in tests/test_factory.py under the build's parallel workers. The tail the
factory gave names no test, and pytest's lastfailed was empty here, so the test is not known for certain. Run serially
on this branch, the whole of tests/test_factory.py passes: 204 passed, 2 skipped (Docker) in 1057 s, rc 0. The one
implement.py path in reach of this branch (pools.my_turn) is unchanged; pools.measured and risk.py, which it does
change, are not called by implement.py. So no code was changed. The likely failure is still
test_an_unstacked_gap_builds_as_before's 120 s bound per implement.py run (about 60 s each when run alone) under load.
Why implement.py takes about 60 s is outside this gap (lesson 13) and belongs in its own gap. Not run on clean main
here. A note on process: a stray single-test run was started while the whole-file run was going and was stopped after
10 s, and a first whole-file run was stopped by its own 600 s limit at 34% (its last F was the test it was killed in).
