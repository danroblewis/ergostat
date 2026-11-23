# remote-and-libraries-explain-remote-parts: explain names a remote's parts and the loops that cross into a remote

depends-on: []

Problem: remote-systems.md §6: 'Loops are found through remote parts ... explain names the remote parts on it'. ergostat/spec/explain.py:141-157 (feedback) lists every loop with no remote marking, and neither a part's nor a system's explanation (explain.py:389, :495) says a part is a remote's, where it runs or how old its readings are, although docs/AGENT-GUIDE.md §3a tells agents to use `ergostat explain system.incidents` to look before referencing. remote_of (ergostat/remote/__init__.py:9) and box (:61) already know it.
Change: explain says remoteness wherever it names a part.
Definition of done:
1. Explaining a part that remote_of names starts with 'remote NAME's (runs at URL, model vM, read T ago | not answering)', from remote.box, and for a block says it is never run here.
2. explain system.NAME for a remote's box system says the same once, then its served systems and parts as today.
3. In the feedback list, a loop with any remote part ends with ' (crosses remote NAME: part, part)'; a goal's explanation whose loop reads a remote part says the remote's part is a measured input there (a disturbance or a setpoint handed to us), never an actuator.
4. The MCP explain tool returns the same text (it calls explain), and nothing changes for a model with no remotes (the existing explain tests pass).
5. AGENT-GUIDE §3a step 2 says what explain shows.
Files: ergostat/spec/explain.py, docs/AGENT-GUIDE.md, tests/test_remote.py.
Acceptance tests: test_explain_marks_remote_part (a planted remote, explain of stock.incidents-open names the remote and its version); test_explain_loop_crossing_remote (a local goal whose controller's flow drives a remote stock that drives a local one: the loop line names the remote's parts); test_explain_without_remotes_unchanged (golden text of a demo model unchanged).
Size budget: 80 net lines.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built: all five points, about 33 net lines of code, inside the 80-line budget. Choices made alone, each easy to undo:
- ergostat/remote/__init__.py, which is not in the Files list, gets one added key: box() returns its state words as
  `now`, so explain doesn't have to parse them back out of `says`.
- The golden file (tests/golden/explain-alert-triage.txt) is examples/alert-triage's whole explanation and every
  part's and system's. It was written by the test itself, once, from main's explain.py before this gap changed it
  (commit 2cf215fd). The branch that wrote it was then removed.
- A goal's "reads a remote's parts" line counts its goal's measure, the parts the loop goes through, its
  disturbances and their driven-by causes, and its blocks' inputs.
- The MCP explain tool calls explain(), so it is covered by the same code. No separate MCP test was added.
Not run here: the unit suite, the browser files (no page changed) and demo_check (no example changed).

Round 2 (the review's one finding, the golden text holding host paths):
- _every_explanation in tests/test_remote.py now replaces this host's interpreter (library/expand.py PY, the
  quoted sys.executable) with `<python>` and the templates folder (library/templates.py HERE) with `<templates>`,
  and the golden file has the same placeholders in its three lines. The golden file has no `/work`, `/opt`,
  `/Users` or `venv` left in it. No code outside tests changed.
- Seen failing: with "  Reads: " changed to "  Reads:  " in explain.py, test_explain_without_remotes_unchanged
  failed (AssertionError); restored, it and all 15 tests of tests/test_remote.py pass; ruff clean.
- Not shown: a run from a second checkout and venv (a clone under /tmp with its own .venv) was refused in this
  session, so the host independence rests on the placeholders being taken from the same PY and HERE the output uses.

Round 3 (the queue: test_explain_without_remotes_unchanged failed alone after main was merged in):
- Cause: the golden text held alert-triage's `uses: modelling` system, whose description is library template text.
  Main reworded it (89083c72 dropped "(SPEC §12e)"), so the golden went stale with no change to explain.py. Main's
  explain.py is unchanged since 2cf215fd (`git diff 2cf215fd main -- ergostat/spec/explain.py` is empty).
- Fix, tests only: the test copies examples/alert-triage to tmp_path and cuts its `uses:` block, so the golden holds
  the example's own parts only and no longer moves when main rewords a library template. The golden was rewritten.
  The test also asserts that the cut model has no modelling system. Easy to undo: the golden and one helper.
- Why the rewritten golden is main's text: checking out main's explain.py to write it was refused in this session,
  so the branch wrote it. Before that, the branch's output for the whole uncut example was diffed against the old
  golden (written from main's explain.py). The only differing line was the reworded template description.
- Seen failing: with "  Holds " changed to "  Holds  " in explain.py, the test failed (AssertionError). Restored, all
  17 tests of tests/test_remote.py pass and ruff is clean. main (2a97eafb) is already merged. No code outside tests
  changed.
- Refused in this session: a python heredoc editing the test, a scratch script under /tmp (both writing and running
  it), and `git checkout main -- ergostat/spec/explain.py ergostat/remote/__init__.py`.
