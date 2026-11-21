# modelling-improves-the-model: the AI tier gets a daily spending cap it can enforce and ceilings on its counts, so the gap can be marked done
depends-on: []

Most of this gap is already on main: modelling-core and modelling-core2 landed the requests (`numbers/requests.py`), the rule tier (`numbers/rules.py`), the AI tier (`numbers/modeller.py`, `library/run/modelling.py ai`), the judge's change classes, the one-line status (`numbers/modelling_status.py`) and `use: modelling` in every example. None of that is rebuilt here. The parked parts (the rule tier's first-order equations, event-type renames that edit programs, the rule tier's copies of the chain fixes) stay parked on `selfimprove`.

Two gaps are left before GAPS can say done:
- **No daily cap.** The redesigner stops at `redesign.daily` (`modelling.py redesign`), and repair stops at its own `daily` (`repair/fix.py ledger`). The AI tier has no cap, and the AI tier is the part that runs every `ai-every` on every example with `ai: true`.
- **No ceilings (lesson-4).** `--most` (requests in one call, so prompt size and cost), `--tries` (calls on one request across runs) and the template's `ai-most` have no maximum, and template parameters have no `min:`/`max:` at all.

## Definition of done

1. **A ledger for the AI tier** (`ergostat/numbers/modeller_spend.py`, new). It lives at `<p.dir>/modelling/ai-spend.jsonl`, guarded by an `fcntl` lock on `<p.dir>/modelling/ai-spend.lock`, following `repair/fix.py ledger`. It holds two kinds of row:
   - `{"id", "time", "reserved"}`, written before a call;
   - `{"id", "usd", "estimated"?}`, written after it.

   The day's spend is computed per id. A settled id counts its `usd`; an id with no settle row counts its whole `reserved`. Each id is dated by its **reservation row's** time and counted when that time is within the last 86,400 s. A settle row is never dated by its own time, so a correction can never fall into the window without its reservation and push the day's spend below what was spent.

   A missing file is an empty ledger. A file that exists but cannot be read or parsed (any bad line, a missing key, a non-number) means **no call** (it fails closed), and the reason is given.

2. **The cap is checked before every call, and the lock is held through the call.** This includes the second call in a run: `modeller.answer`'s go-back, which gives the AI the changes ergostat turned away. `answer` takes a way to make each call within the ledger (for example a context-manager factory given that call's prompt).

   For each call, the reservation is `modeller.unsaid(prompt, model)["usd"]` for that call's own prompt. Under the lock:
   - the day's spend is read;
   - if `spent + reserved > daily`, no call is made and the run stops there (it says why on the log line);
   - otherwise the reservation row is written, the call made, the settle row written, and only then is the lock released.

   With the lock held across the whole step, two `modelling ai` processes cannot both take the last of the cap. AI-tier calls run one at a time; the redesigner's and repair's calls are not covered.

   A call that errors is charged what `call()` returns: its whole `unsaid` estimate, flagged `estimated`. As today, the run makes no further call after an error.

3. **The reservation goes to claude as its budget, and the docs stop at what that guarantees.** When the AI command is `claude`, `modeller.call` passes `--max-budget-usd` with the reservation (as `decisions/ai.command` does). Neither the reservation nor that flag is proven to be a ceiling: Claude Code checks its budget after a turn, and `unsaid` does not count Claude Code's own system prompt. So:
   - a call that reports more than its reservation is charged **what it reported**;
   - the log line says the overrun (`$X over its $R reservation`);
   - since the day's spend is then at or over the cap minus less than one reservation, no further call starts that day until older charges leave the window.

   SPEC, the template's description and `self-improvement.md` say exactly this: *a call starts only when the day's spend plus its reservation stays within `ai-daily`; one call at a time; a call that reports more than its reservation is charged what it reported, so the day can end above `ai-daily` by that one call's overrun, and none starts after it until the day's spend is back under.* None of them says the AI tier spends "at most `ai-daily` a day".

4. **A run stopped by the cap leaves its requests untouched.** No `tried.ai` increment, no `held` with the AI's reason, no `cost_usd` share for a call never made, so a capped run does not count against `--tries` (as repair's capped failure is not counted as an attempt). If the cap stops the go-back after a first call that was made, the requests in that first call are counted and charged as now.

5. **Ceilings on every count that multiplies calls or money,** enforced at config time and again at run time:
   - **Config time.** Template parameters accept `min:` and `max:` (`library/templates.py Param`, `library/expand.py coerce`). A value outside them is an `ExpandError` that names the bound. The modelling template sets:
     - `ai-most` {min 1, max 16};
     - a new `ai-daily` (number, dollars a day, default 1, min 0, max 20), passed as `--daily ${ai-daily}`.
   - **Run time.** `modelling ai` refuses with exit code 2 and an argparse error when:
     - `--most` is outside 1..16;
     - `--tries` is outside 1..3;
     - `--daily` is outside 0..20, or is not given (no default).
   - The block's run line in `template.yaml` passes `--daily`.

6. **The status says the cap.** `modelling_status.of` (and so `ergostat status` and the Model page's line), when the AI tier is on:
   - says `the AI tier has spent $X of its $Y today` once a call has been refused for the cap today, or when the spend is within one reservation of the cap;
   - says `the AI tier's spend ledger cannot be read: no AI call` when it can't be read.

   The returned dict carries `ai_spent` and `ai_daily`.

7. **Docs are current:**
   - SPEC §12e (the AI tier paragraph and the template parameters), with `min:`/`max:` added where SPEC lists template parameter keys;
   - `docs/proposals/self-improvement.md` (one paragraph on the cap, in the words of item 3);
   - `docs/GAPS.md`: the entry moves from *landing* to **done**, still naming what is parked on `selfimprove`;
   - the template's `ai`/`ai-daily`/`ai-most` descriptions.

8. **The usual done.** Every acceptance test exists and passes. The unit suite and the four browser files pass with rc 0 and no page test skipped for want of a port. Ruff is clean. `demo_check` passes on image-squeeze, alert-triage, ticket-factory and the-job, since the template change reaches every example's expansion. origin/main is merged in and the suites are run again.

## Files to touch

- `ergostat/numbers/modeller_spend.py` (new: the ledger, the day's spend, reserve/settle under the lock)
- `ergostat/numbers/modeller.py` (`answer` makes every call through the ledger; `call` passes `--max-budget-usd` when the command is claude)
- `ergostat/library/run/modelling.py` (`ai`: `--daily`, bounds on `--most`/`--tries`/`--daily`, capped runs leave requests untouched, overrun said)
- `ergostat/library/templates.py`, `ergostat/library/expand.py` (`min:`/`max:` on parameters)
- `ergostat/library/templates/modelling/template.yaml` (`ai-daily`, bounds on `ai-most`, the run line)
- `ergostat/numbers/modelling_status.py` (the cap in the line)
- `docs/SPEC.md`, `docs/proposals/self-improvement.md`, `docs/GAPS.md`
- `tests/test_modelling_ai_cap.py` (new)

## Risks

- **lesson-3 (failing open):** the cap could be checked as `spent >= daily` instead of `spent + reserved > daily`. An unreadable ledger could count as empty (the existing `common.kept` helper does exactly that on bad JSON, so it must not be used). An unsettled reservation could count as zero. A correction row dated by its own time could fall into the window without its reservation and make the spend look smaller.
- **lesson-8 (a claim wider than the code):** the docs could say "at most `ai-daily` a day" when a call can report more than its reservation. Item 3's wording is the only claim allowed, and `test_a_call_that_costs_more_than_its_reservation_is_charged_what_it_said` is the test that holds it.
- **lesson-9 (a test that can't fail):** the go-back test must really reach the second call, and the cap test must sit in the window between `spent >= daily` and `spent + reserved > daily`. Each test below names the break that makes it fail, and the implementor makes that break and reports the failure.
- **lesson-1 (check then write without the lock):** the lock could be taken for the check and released before the reservation row, or before the call, so two runs both take the last of the cap.
- **lesson-4 (a floor and no ceiling):** `--most`, `--tries`, `ai-most`, `ai-daily`, `--daily` need hard maxima at both config time and run time, or the template is bounded but a hand run is not.
- **lesson-2 (ordering by wall time):** settle rows must be matched to reservations by `id`, never by time order or "the latest row".
- **lesson-5 (stale state under a reused id):** reservation ids must be fresh (uuid4), never derived from the request or the run, or a settle row from an earlier call settles a new reservation.
- **lesson-6 (work after cancel):** a run killed mid-call never writes its settle row. That counts the whole reservation (fail closed), and the lock is released by the kernel when the process dies. `test_a_call_left_unsettled_counts_whole` covers the charge; nothing new is spawned beyond today's single `subprocess.run`.
- **lesson-7 (two things merged):** the new `--daily` flag and template parameter must survive a merge of origin/main; the suites run again after the merge.
- **lesson-13 (stay inside the gap):** the redesigner's own `cost["usd"] >= budget` check (`redesigner.py:244`) and repair's ledger are not changed here. A suite failure in them is reported, not fixed.

## Acceptance tests

All in `tests/test_modelling_ai_cap.py`. The AI is a stand-in: `modeller.call` monkeypatched, or `subprocess.run` patched where the command line matters. It counts its invocations and reports a set `usd`. The project is a small model with `use: modelling` and `ai: true`, and AI-tier requests open.

- `test_a_call_starts_only_within_the_days_cap`
  - Setup: the ledger holds a settled day's spend S. With `--daily` D where S < D < S + R (R the reservation for this prompt), `ml.ai` makes **0** calls and the log names the cap.
  - Shows: with D ≥ S + R, one call is made, and the ledger then has exactly one reservation row and one settle row, under the same id.
  - Fails if: the check is `spent >= daily`.

- `test_the_go_back_checks_the_cap_again`
  - Setup: the first answer proposes one change that `im.trial` (monkeypatched) turns away, so `answer` would go back. The first call reports a cost that leaves less than the second prompt's reservation under D.
  - Shows: exactly 1 call, no second reservation row, and the requests in the first call counted as tried once.
  - Fails if: the ledger is consulted only before the first call (2 calls, 2 reservations).

- `test_a_failed_call_is_not_tried_again_in_the_run`
  - Setup: the stand-in raises `TimeoutExpired`.
  - Shows: 1 call; the ledger charges that call's whole `unsaid` amount, with `estimated`.
  - Fails if: an errored call is retried, or charged 0.

- `test_the_next_run_checks_the_cap_and_a_capped_run_burns_no_try`
  - Setup: two `ml.ai` runs; after the first, the second's reservation would pass the cap.
  - Shows: the second makes 0 calls, and every request's `tried.ai`, `state` and `cost_usd` are unchanged by it.
  - Fails if: a capped run increments `tried` or marks requests `held`.

- `test_a_call_that_costs_more_than_its_reservation_is_charged_what_it_said`
  - Setup: the stand-in reports 3R; D lies between S + R and S + 3R.
  - Shows:
    - the day's spend is S + 3R (not S + R), and the log says the overrun;
    - a following run makes 0 calls;
    - `modelling_status.of(p)["ai_spent"] == S + 3R`.

    So the day ends above D by at most that one call's overrun, as the docs say.
  - Fails if: the settle row writes the reservation instead of the reported cost.

- `test_the_reservation_is_claudes_budget`
  - Setup: with the AI command named `claude` (a stub on PATH or `subprocess.run` patched), the command line is captured.
  - Shows: the captured command line carries `--max-budget-usd` equal to `unsaid(prompt, model)["usd"]` (as formatted).

- `test_an_unreadable_ledger_means_no_call`
  - Setup: a ledger with one unparsable line, then one with a row missing `reserved`.
  - Shows: 0 calls each time, the log says the ledger cannot be read, and the status says `cannot be read`. A missing file still allows a call.
  - Fails if: a bad ledger is read as empty.

- `test_a_call_left_unsettled_counts_whole`
  - Setup: a reservation row with no settle row, within the day.
  - Shows: it counts at its `reserved` in `modeller_spend.spent`.

- `test_a_charge_is_dated_by_its_reservation`
  - Setup: a reservation at now − 86,400 − 10 with its settle row at now − 86,400 + 50, and another reservation at now − 100 settled now.
  - Shows: the first counts 0 (not negative, not its correction), the second counts its settled `usd`.
  - Fails if: settle rows carry their own time, or corrections are summed as deltas.

- `test_two_runs_cannot_both_take_the_last_of_the_cap`
  - Setup: two threads each reserve against a cap that fits exactly one reservation. The stand-in call is monkeypatched to wait on a barrier, so the second thread tries to reserve while the first is mid-call.
  - Shows: exactly one call, exactly one reservation row.
  - Fails if: the lock is released before the call or before the reservation row.

- `test_ai_counts_and_dollars_have_a_ceiling`
  - Config time: expanding the modelling template with `ai-most: 500` or `ai-daily: 1000` raises `ExpandError` naming the max. A plain test template with `max: 3` refuses 4 and accepts 3, and with `min: 1` refuses 0.
  - Run time: `ml.ai` with `--most 500`, `--tries 9`, `--daily 1000`, or no `--daily`, exits 2 (`SystemExit`) and makes 0 calls. In-range values run.

- `test_the_status_says_the_cap`
  - Setup: after a capped run.
  - Shows: `modelling_status.of(p)["says"]` contains `of its $` with the day's spend and the cap. With the AI tier off, it says nothing about spend.

Also run, unchanged and passing: `tests/test_modelling_core.py`, `tests/test_modelling_core2.py`, `tests/test_self_improve.py`, `tests/test_modelling_template.py`, `tests/test_improve.py`.

For each new test, the report says which break was made in the code and that the test then failed (lesson-9).

## Size budget

250 net lines of code outside `tests/` and `docs/`; expected about 170:
- ledger about 60;
- `modeller.py` about 25;
- `modelling.py ai` about 35;
- parameter `min:`/`max:` about 20;
- template about 10;
- status about 20.

## Notes from the plan review (answer each)

- Ledger parse must reject non-finite (NaN/Infinity, which json.loads accepts) and negative reserved/usd as unreadable; add both to test_an_unreadable_ledger_means_no_call.
- A reservation that is not finite and >0 means no call, so --daily 0 can never pass a call through; add a test that --daily 0 with a 0 reservation makes 0 calls.
- test_two_runs_cannot_both_take_the_last_of_the_cap: a barrier inside the call deadlocks under a correct lock, and lockf does not block between threads of one process. Use two processes with flock on a fresh open, coordinated by an event plus a bounded wait or a LOCK_NB probe during the first call.
- Item 6: say where a cap refusal is recorded (e.g. a 'refused' row the parser accepts and the spend ignores) and which reservation 'within one reservation' means. The status read must not block on the call lock or report a half-written last line as unreadable.
- A reservation time in the future (clock stepped back) counts in the window; add a test.
- Killing the parent mid-call leaves the claude child running unlocked and uncharged beyond its reservation: kill the process group on parent death or timeout, or narrow the docs' claim.
- Confirm no existing caller or test passes --tries above 3.

## Where it stopped

Built: items 1 to 7, with every acceptance test in `tests/test_modelling_ai_cap.py` (22 tests, all passing). About 218
net lines of code outside tests and docs, within the 250 budget.

**Lesson-9 breaks.** Each break below was made in the code, the named tests failed, and the code was put back:
- cap as `spent >= daily`: `starts_only_within_the_days_cap`, `go_back_checks_the_cap_again`,
  `next_run_checks_the_cap...` failed;
- lock released after the check, before the reservation row: `two_runs_cannot_both_take_the_last_of_the_cap` failed;
- settle row writes `min(usd, reserved)`: `costs_more_than_its_reservation...` failed;
- an errored call charged 0, and an unsettled reservation counted as 0: `failed_call_is_not_tried_again`,
  `call_left_unsettled_counts_whole`, `reservation_dated_in_the_future_counts` and
  `half_written_last_line...` failed;
- a settled id counted whatever its reservation's time: `charge_is_dated_by_its_reservation` failed;
- an unreadable ledger read as empty: all 7 `unreadable_ledger` cases failed;
- the go-back made outside the ledger: `go_back_checks_the_cap_again` failed. `go_back_is_made_within_the_cap` (added)
  shows that the go-back is really reached when there is room;
- a capped run still counting tries: `next_run_checks_the_cap_and_a_capped_run_burns_no_try` failed;
- `--max-budget-usd` not passed: `reservation_is_claudes_budget` failed;
- `ai-daily` max 2000, and separately `--most` max 1600: `ai_counts_and_dollars_have_a_ceiling` failed each time;
- status said only when near the cap, not after a refusal: `status_says_the_cap` failed.

**Answers to the plan review:**
- Non-finite values (NaN and Infinity, rejected through `parse_constant` and `math.isfinite`), negative amounts,
  strings, a missing `reserved`, and a duplicate reservation or settle row for one id all make the ledger unreadable.
  Each kind of row is a parametrized case of `test_an_unreadable_ledger_means_no_call`.
- A reservation that is not finite and above 0 raises `Capped` before the lock is taken.
  `test_a_daily_of_0_or_a_reservation_of_0_makes_no_call` covers `--daily 0`, a 0 reservation, and a 0 reservation
  with `--daily 20`.
- The two-runs test uses two forked processes, each opening the lock file fresh. The parent probes with `LOCK_NB`
  while the first is mid-call, and shows that the second blocks (bounded 1 s wait) until the first is released.
- A refusal is recorded as a `{"refused": time, "reserved"}` row: the parser accepts it, and the spend ignores it.
  "Within one reservation" means the latest reservation row in the file (file order, not time). The status reads
  without the lock (`today`, `partial_ok`), and a last line with no newline yet is left out. Under the lock, the same
  partial line counts as unreadable (fail closed); `test_a_half_written_last_line_is_left_out_by_the_status_only`
  covers both.
- A reservation dated in the future counts (`r["time"] > now - DAY` has no upper bound):
  `test_a_reservation_dated_in_the_future_counts`.
- Killing the parent mid-call: I took the reversible option and narrowed the claim, without adding process-group
  handling. SPEC says the lock "does not reach a claude child that outlives a killed run". The run is still charged its
  whole reservation, as no settle row is written.
- `--tries`: no caller or test passes it at all (the template's run line does not), so none passes it above 3.

**Deviations and decisions (no one to ask; each is the more reversible option):**
- `tests/test_modelling_core.py::test_the_redesigner_and_the_ai_tier_print_result_lines` called `ml.ai` with no
  `--daily`, which item 5 requires to exit 2. Its one call now passes `--daily 1`; the test is otherwise unchanged.
- `ai-most` became `type: integer` (it was `number`), because `--most` is an int and 2.5 would have expanded to a run
  line argparse refuses.
- The status reads `ai_daily` from the `modeller` block's expanded run line (`--daily N`). A hand run with another
  `--daily` is reported against the block's cap.
- `docs/ADDING.md`'s example comment names the new bounds.

**Not run here:**
- `demo_check` on image-squeeze, alert-triage, ticket-factory and the-job: this sandbox denied the command (it starts
  engines and a server). In its place, `tests/test_chains.py`, `tests/test_blockdiagram.py` and
  `tests/test_modelling_template.py`, which load every example with the new template, pass (103 tests).
- The full unit suite and the four browser files: left to the factory's watchdogged run, as the instructions say.
- Merging origin/main: this clone has no `origin` remote, and local `main` is already in HEAD. The merge and the second
  run of the suites are left to the factory.

**After the factory's unit run (one failure):** `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth`
failed once in the factory's `-n` run (a lease still held after `close`). It passes alone and beside this gap's tests
(77 and 20 passed). This branch changes nothing in leases, the engine or the runner, so the lease code is not changed
here (lesson-13). The one way this branch could reach another test in the same worker was
`test_two_runs_cannot_both_take_the_last_of_the_cap`, which `fork`ed the multi-threaded xdist worker (the
DeprecationWarning in that run) and joined only its first child. It now uses `spawn`, joins and kills both children,
and waits until the second is up before asserting it is held off by the lock. Broken again by releasing the lock
before the call: it fails.
