# ai-call-failures-are-failures: a failed AI call is recorded as failed and charged

depends-on: []

Audit of `ergostat/numbers/modeller.py` `call()`: it ignores the process's exit code and the response's `is_error`, and a missing `total_cost_usd` becomes $0. Demonstrated with a stand-in: during a 429 outage each run recorded $0, used up a try, and the requests ended `held` with "the ai tier proposed nothing", the 429 appearing nowhere. With a cap fitting one call, a response with no cost allowed 3 of 3 calls.

## Definition of done
- A non-zero exit, `is_error`, or a missing or invalid cost returns an `error` carrying what the call said, charged at the reservation (`unsaid`), as a timeout already is.
- An errored call does not use up a request's tries and never reads as "proposed nothing". The error is visible on the request.
- Every caller sharing `call()` (modeller, reviewer, redesigner) handles it.

## Files to touch
`ergostat/numbers/modeller.py`, `ergostat/library/run/modelling.py`, the tests of the AI tier.

## Risks
- lesson-3: an unknown cost is charged as the most it could be, never $0.

## Acceptance tests
- `tests/test_modeller.py::test_a_failed_call_is_an_error_and_keeps_its_try`
- `tests/test_modeller.py::test_an_is_error_response_is_an_error`
- `tests/test_modeller.py::test_a_response_with_no_cost_is_charged_its_reservation`
- `tests/test_modeller.py::test_the_cap_holds_when_responses_omit_their_cost`

## Size budget
50 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1: 34 net lines outside `tests/` and `docs/` (48 added, 14 removed). The four acceptance tests pass, and
so do three more in `tests/test_modeller.py`: a good call is charged what it said, the reviewer's failed calls are no
try, and a redesigner run whose calls failed ends `error`. Each new guard was broken once and its test seen to fail.

Choices made alone (the most reversible one each time):
- `call()` charges a failed call its reservation, or the cost it said if that is more (a call over its budget can say
  more than `unsaid`). A cost counts as said when it is a finite number, 0 or more, and not a bool. A said `$0` on a
  successful call is believed.
- The AI tier: when its first call fails, its requests keep their state and tries, are charged their share, and carry
  `why` and `error`. They wait for the next run, which can call again during an outage. Only the daily cap bounds
  those calls, each charged its whole reservation. When the go-back call fails after a first answer, that first answer
  used the try as before, and the held `why` says the second call failed rather than "proposed nothing".
- "Every caller" reached two files outside "Files to touch", in a few lines each. `numbers/reviewer.py`: a failed call
  is stamped `error`, does not count in `tries()`, and stops the pass. `numbers/redesigner.py` with
  `numbers/redesign_due.py`: the run's result is `error`, its request stays open saying so, and the unit takes no rest
  for it. SPEC §12e says all of this.
- This clone has no `origin` remote, and its `main` is the branch's base, so there was nothing newer to merge. The
  merge and the full suites are left to the factory.

### After the factory's unit run (round 1)

The factory reported `unit` failed, but the tail it gave stops partway through, at 81%. It shows no failed test, no
pytest summary, and no closing JSON line from `suite_watch`, so the run was cut off rather than ending on a failure,
and the tail names no test. Nothing in the code was changed for it. Without a failing test named, any change would
be a guess.

Run here, one file at a time, all passing: `test_modeller` (13), `test_modelling_ai_cap`, `test_redesign`,
`test_redesign_memory` (59 with `test_modeller`), `test_modelreview` (21), `test_modelling_core`,
`test_modelling_core2`, `test_sd_review`, `test_inbox`, `test_improve`, `test_self_improve`, `test_redesign_bench`
(114), `test_modelling_template`, `test_mended`, `test_templates`, `test_unmoved`, `test_daemons_restart` (70),
`test_web_access`, `test_factory` (108, 2 skipped). The new tests take under 0.6 s each. Not run here: the whole
unit suite (the session was not permitted to run it), so where it stopped is unknown.

Checked and ruled out:
- A loop that never stops. The modeller and the redesigner run on `every:` schedules, not on request events, so a
  failed call that keeps its try cannot set off its next run at once.
- A thread left behind. `tests/conftest.py` starts no threads or processes for the session.

Left: the factory's full unit run, with its output past 81% (or `-o faulthandler_timeout=240` to name a test that
hangs), and the fix if a test is named.

### Round 2: failed calls bounded per item

Answering review/ai-call-failures-are-failures-1, every finding:

- lesson-4 (blocking), a failed call never counted, so one that fails the same way every time was called without end
  and starved the queue behind it. Failed calls now have their own count and a bound, `modeller.FAILS = 3`, a
  constant (not config), shared by the three callers:
  - The AI tier (`library/run/modelling.py`): each request keeps `failed: {ai: n}`. Requests are taken with the ones
    that failed least first. A request that has failed before goes alone in its call, so one bad request does not
    keep sinking a group. At `FAILS` it is held for the owner ("the ai tier's call failed 3 times; it waits for the
    owner: <error>") and is no longer given to the tier. Its tries are still unused.
  - The reviewer (`numbers/reviewer.py`): `tries(p, x, failed=True)` counts a change's failed calls, on the version
    it read. The queue is read with the changes that failed least first. At `FAILS` the change is `undecided`, so the
    owner gets it with the error in its summary.
  - The redesigner (`numbers/redesign_due.py`): a unit whose last `FAILS` runs all ended `error` within `COOL` rests
    as after a run that made nothing. Units already take turns, oldest review first, so a failing unit never starved
    the others.
  - During an outage this hands requests and changes to the owner after 3 failed calls each. I chose that because it
    can be undone: the owner can reopen what was handed over, while unbounded calls cannot be taken back. It is said
    in SPEC §12e.
  - Tests: `test_a_request_whose_calls_keep_failing_does_not_starve_the_others` (a second request gets its call while
    the first keeps failing, and the first gets exactly `FAILS` calls before it is held),
    `test_the_reviewer_gives_a_change_whose_calls_keep_failing_to_the_owner_and_reads_the_next`, and the rest cases
    added to `test_the_redesigner_says_a_failed_call_not_nothing_proposed`. The reviewer test from round 1 now stops
    at `FAILS - 1` failures. I broke each guard once and saw its test fail: the bound in the tier's filter, the
    alone-and-behind ordering, the reviewer's ordering, the reviewer's `FAILS` hand-over, and the redesigner's rest.
- A failed go-back call still uses a try. This is on purpose: the first call gave a real answer. SPEC §12e now says so.
- The round-1 unit run cut off at 81%: the cause is still unknown. This session was not permitted to run the whole
  unit suite either, so nothing new is known about it.

Size: 47 net lines outside `tests/` and `docs/` against `main` (69 added, 22 removed), within the 50 budget.
Run here, one file at a time or a few together: `test_modeller` (15), `test_modelling_ai_cap`, `test_modelreview`,
`test_redesign`, `test_redesign_memory` (82 together), `test_modelling_core`, `test_modelling_core2`,
`test_redesign_bench`, `test_sd_review`, `test_inbox`, `test_improve` (104 together), all passing. Ruff is clean.
Not run: the whole unit suite, the browser files, the merge of origin/main (this clone has no `origin`).

### After the factory's unit run (round 2)

The factory reported `unit` failed again, and again the tail it gave stops partway, this time at 97%, in the middle of a
line. It shows no failed test, no pytest summary, and no closing JSON line from `suite_watch`. The run was cut off, and
no test is named. Nothing in the code was changed for it. Without a failing test, any change would be a guess.

Run here, one batch at a time, with `-o faulthandler_timeout=120` (or 240) so a hanging test would have been named:
- `test_modelling_template`, `test_self_improve`, `test_mended`, `test_unmoved`, `test_triggers2`, `test_spec_causal`,
  `test_spec_items`, `test_spec_mcp_explain`, `test_reports`, `test_recipes`, `test_goal_per`, `test_item_systems`,
  `test_interventions`, `test_churn`, `test_backlog`, `test_control`, `test_decisions`, `test_cli_fallback`,
  `test_numbers`, `test_modeller`, `test_modelling_ai_cap`: 350 passed and 1 failed, in 219 s, with no hang.
  - The failure is `test_modelling_ai_cap.py::test_two_runs_cannot_both_take_the_last_of_the_cap`. It depends on test
    order and this branch did not cause it. Its spawned child failed with `ImportError: cannot import name 'Empty'
    from 'queue' (/work/dev/bin/queue.py)`: an earlier file in the same process (`test_backlog` puts `dev/bin` on
    `sys.path`) leaves `dev/bin/queue.py` in front of the standard library's `queue`. Run alone, the file passes,
    22 of 22. The branch does not change either file, `sys.path`, or `dev/bin`. Reported, not fixed (lesson-13).
- `test_templates`, `test_daemons_restart`, `test_web_access`, `test_agents_page`, `test_blockdiagram`, the
  `test_factory_*` files (`knowledge`, `manager`, `resources`, `sessions`, `times`), `test_repair2`, `test_parity`,
  `test_intent`: 276 passed and 33 skipped, in 274 s, with no hang.
- Ruff is clean.

Checked by reading the code: every stand-in in the tests that reaches `modeller.call` says a `total_cost_usd`, so none
of them turns into an endless "failed call". Every path for a failed call is bounded: the tier holds a request after
`FAILS`, the reviewer stops the pass, and the redesigner rests after `FAILS` errors.

Not run: the whole unit suite (again not permitted in this session) and the browser files. Left: the factory's full
unit run with its output past the cut-off, or with `-o faulthandler_timeout=240` so a hanging test is named, and the
fix if one is named.
