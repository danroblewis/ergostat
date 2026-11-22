# remote-and-libraries-remote-parts-are-data: A remote's parts are data here: never integrated, fitted or judged unexercised locally

depends-on: []

Problem: remote-systems.md §6 and SPEC §4c say a remote's stocks are endogenous there and exogenous here: read as data series, never integrated; the local residuals, coherence and 'not exercised by the record' leave its parts out. On main the served flows keep their equations (ergostat/remote/serve.py:26, 'equation' in PART_KEEP['flows']), compose drops one only when it names a part left out (ergostat/remote/compose.py:440), and ergostat/numbers/simulate.py:96 integrates every stock with flows, so a remote's stock is integrated in the local replay and the projection (open and closed loop), and ergostat/numbers/fit.py:211-217 puts it in the local fit total that the modelling goals hold. ergostat/numbers/exercised.py:56-117 judges remote parts 'never-moved'/'no-variation'. ergostat/remote/__init__.py:18-21 claims the exclusion, but only state.py:193 and :623 apply it.
Change: one helper decides what is a remote's (remote_parts, already there); simulate.plan leaves remote stocks out of what it integrates by default (taken as measured, like `given`), and the projection carries them as inputs (held or trended, as any input); the fit total, the residual examination and the exercised findings skip remote parts. The remote's flow equations stay as they are: the equation finder and the estimate still use them for texts written for the remote's owner (numbers/remote_text.py), which must keep working.
Definition of done:
1. simulate.plan(spec) with integrate=None integrates no stock in remote_parts(spec); each is 'given' in Run.how and a note says 'stock.X is remote NAME's: taken as read, never integrated here'. An explicit integrate= set is honoured as given (callers that ask still get it).
2. simulate.project and closedloop.closed carry a remote stock as an input (inputs='hold' or 'trend', as every other input), never as integrated state; a local flow from or to a remote stock still moves the local stock.
3. fit.compare leaves remote stocks out of 'stocks', 'accounting' and 'total' and lists them under a new key 'remote' (ref -> remote name), so the local model-error goal is not moved by a remote's dynamics.
4. residuals (examinable/unread) and exercised.quiet/findings skip remote parts.
5. Texts for a remote's owner (remote_text) are made exactly as before: tests/test_remote_proposals.py passes unchanged.
6. SPEC §4c says this in one paragraph (what is given, what is left out, what still uses the remote's equations); GAPS's remote entry says it is done.
Files: ergostat/numbers/simulate.py, ergostat/numbers/fit.py, ergostat/numbers/residuals.py, ergostat/numbers/exercised.py, ergostat/remote/__init__.py (docstring), docs/SPEC.md, docs/GAPS.md, tests/test_remote_analysis.py (new).
Acceptance tests (tests/test_remote_analysis.py, a local model composing a planted remote cache as tests/test_remote_chain.py does, with recorded readings): test_remote_stock_is_given_not_integrated (Run.how is 'given' and the replayed value equals the readings; fails if plan integrates it); test_projection_carries_remote_stock_as_input (hold: flat at its last reading; a local flow drained from it still moves the local stock); test_fit_total_leaves_remote_out (a remote stock whose readings the remote equation fits badly leaves the local total unchanged and is listed under 'remote'); test_exercised_skips_remote (a flat remote stock gives no never-moved finding; a flat local one still does); the existing remote proposals tests pass.
Size budget: 140 net lines outside tests and docs.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Round 1, 2026-11-22. The code, the docs and the acceptance tests are written, but **none of it has been run or
committed**. Every Bash command in this session was refused ("don't ask mode"; the first one was `cat
dev/records/remote-and-libraries-remote-parts-are-data.md | head -5; wc -l ...`, and then even `git -C /work log
--oneline -1`), so no pytest, no ruff, no `git add`/`git commit` and no merge of main could run. The changes are
uncommitted in the worktree. This section is uncommitted too.

Done (written, not run):
- simulate.py: `Plan.remote` (stock → remote). With `integrate=None`, `plan` leaves every stock in `remote_parts` out of
  `integrate`; an explicit set is honoured as given. The replay notes 'stock.X is remote NAME's: taken as read, never
  integrated here', marks it `given` in `Run.how` and reports its values as read (`Data.level_at`). `project` (and so
  `closedloop.closed`, which goes through it) carries it as an input from `ahead` (held or trended) and reports it,
  `given`, never in `state`, never blanked as downstream of a controller.
- fit.compare: remote stocks out of `stocks`, `accounting` and `total`, listed under `remote` (ref → remote name),
  whatever replay is compared (so a replay that asked for one by name still leaves it out of the total).
- residuals: `unread` leaves remote stocks out; `examinable` says a remote's stock is examined there, never here.
- exercised.quiet (and so `findings` and `parameter_quiet`): remote flows, stocks and auxiliaries are not judged, and
  remote flows do not count toward the typical flow a local one is compared with.
- remote/__init__.py docstring, SPEC §4c paragraph "Its parts are data here", GAPS remote entry's Done.
- tests/test_remote_analysis.py: the four acceptance tests, plus `closed` and `inputs="trend"` in the projection test
  and `residuals.examinable`/`unread` in the exercised test.

Outside the Files list, and why (the most reversible way to keep done items 2 and 5 true):
- numbers/estimate.py: `estimate()`'s two default replays (`base`, `at_best`, which give the slowest time constant an
  estimate is judged on) now ask for every stock with flows by name, so a remote parameter's time scale, and so the
  texts for its owner, stay exactly as before. Without this the remote's stock would have no time constant there.
- numbers/sensitivity.py: the sampled projections' integrate set leaves remote stocks out, so the bands carry a
  remote's stock as an input as the base projection now does, not integrated.

Left:
- Run `uv run python scripts/named_tests.py tests/test_remote_analysis.py` and `tests/test_remote_proposals.py`, ruff, and
  the build suite; fix what fails. Nothing here has been seen to pass, and no test has been seen to fail with the code
  it guards broken (lesson 9): the intended breaks are `plan` integrating remote stocks again (fails the first three
  tests) and `quiet` judging remote parts (fails the fourth).
- Commit (`git add` of the files above and this record), merge main and run the suites again.
- Not touched, outside this gap: docs/GAPS.md's remote entry already carries a spliced, duplicated second Done/Left
  passage (from an earlier merge); it is left as it was.
