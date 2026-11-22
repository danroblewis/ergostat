# architecture-per-system-redesign: each system's redesign is given its architecture, and a daily review on a larger model says which systems to redesign
depends-on: []

The AI rung of the architecture review (`docs/proposals/architecture.md`, *The ladder*; GAPS' Modelling entry
"System architecture review", *Left*: "the per-system redesign and daily larger-model review (after `redesign`)").
`redesign` is merged. What exists and is NOT to be rebuilt:
- units per system (`numbers/redesign_due.py::units`, a system over `MOST_PARTS` taken a subsystem at a time);
- each unit's daily review and the rests (`triggers`, `resting`);
- the shared daily cap (`redesign.spent`, checked in `library/run/modelling.py::redesign`).

Two things are missing:

1. **A redesign of one system is not shown that system's architecture.** The architecture notes are about
   `system.NAME`. But `redesign_due._in(spec, unit, "system.NAME")` looks the ref up in `architecture._chains`, which
   is keyed by parts only. So it returns False, and `redesigner._check(..., system)` (through `_mine`) drops the
   notes about the redesigned system itself (`system-splits`, `systems-merge`, `interface`, `time-scales`,
   `purpose`). The prompt also says nothing of the system's size, interface or subsystems.
2. **Nothing reads the model's architecture as a whole with a model larger than haiku** and says where a redesign
   should start. The owner allowed this: `docs/roadmap/overnight-2026-11-19.md`, *Limits*: "The redesign and
   architecture reviews may use a larger model, with their costs recorded".

## Definition of done

**A. The redesign of a system is given its architecture.**
- `redesign_due._in(spec, unit, ref)` is true for a `system.S` ref when S is the unit or lies within it
  (`unit in spec.chain(S)`), and true for every ref when the unit is `model`.
- The result: the architecture notes on the redesigned system, and on its subsystems, are in its prompt's
  "What check finds" section. Notes on other systems are not.
- `redesigner.prompt` has a section `## Its architecture` with:
  - the unit's size (`architecture.size_said`);
  - for a system, its interface from `spec.interface(S)`: each port's part, kind, direction and peers, at most 30
    lines with the rest counted;
  - its subsystems, and whether it is nearly decomposable (`architecture.nearly_decomposable`);
  - for the unit `model`, each top system's size.
- The section is built from the structure alone, with no run and no call.

**B. The daily architecture review (`ergostat/numbers/archreview.py`, a new module).**

*Settings and when it runs*
- The `redesign:` setting of the modelling template gains `review`: a model name, or `off`. The default is
  `sonnet`. This is a decision taken and recorded in SPEC: the gap is the larger-model review, and the owner allowed
  a larger model for it in the overnight note's *Limits*. It is the most reversible form: it exists only with
  `ai: true`, never with `redesign: {when: off}`, stays inside the same daily cap, and `review: haiku` or
  `review: off` changes it.
- `redesign.settings` returns it. The template's `redesigner` block passes it (`--review ${redesign.review|sonnet}`),
  and `modelling redesign` takes `--review`.
- It runs inside the redesigner block's own run (`modelling redesign`), before `rd.plan`, at most once a day.
  - It is due when no `ergostat.model.architecture-reviewed` event exists in the last `DAILY` (86,400 s), whatever
    that event's result (reviewed, failed, or a call that never answered). So a failing call is not retried on every
    run.
  - `when: ask` and `when: off` never run it. `review: off` never runs it.

*What it reads and answers*
- One call (no retry) through `modeller.call`, tools off, on the `review` model. The prompt:
  - a new guide, `library/templates/modelling/architect.md`;
  - the architecture notes `check` gives (the five codes), each system's size, interface counts by kind,
    subsystems, nearly-decomposable line and description;
  - each unit's replay fit (`scorecard.fit`, per stock, grouped by unit);
  - each unit's last redesign result (from `ergostat.model.redesign-ran`);
  - the units too large to redesign;
  - not the YAML. The prompt is cut to at most 40,000 characters, 60 systems.
- The answer is JSON lines `{"review": {"system": S, "advice": A, "says": TEXT}}`. Parsing is by allowlist:
  - `advice` is `redesign`, `split` or `merge`;
  - for `redesign`, `system` must be a unit `redesign_due.units(spec)` can take (or `model` when the model has no
    systems of its own);
  - for `split` and `merge`, it must be one of the model's own systems;
  - `says` is cut to 600 characters;
  - at most 8 findings are taken, the first finding for a unit and advice wins, and the rest are said as dropped.
  - An answer with no finding line is a review that found nothing.

*What it writes*
- Each finding is held as a modelling request through `redesign_due.hold`, under source `redesign` (so
  `requests.sync` does not answer it as "check no longer finds it"), code `review-redesign`, `review-split` or
  `review-merge`, about `system.S`.
- Each request carries `review`: the id of the `architecture-reviewed` event that raised it.
- `review-redesign` is held `open`. `review-split` and `review-merge` are held for the owner (`owner: True`, state
  `held`) and never acted on: they move parts between systems, which is structure, written only with approval.
- A request the review raised before and does not say again is answered ("the architecture review no longer says
  it"), unless it is `proposed` and waiting on its change.
- When the same id is made again, the old fields are cleared: `change` and `why` are reset, and `says` and `review`
  are the new ones (lesson-5).
- The review writes no model change and edits no file.

*The review sets which system is redesigned next*
- `redesign_due.triggers` reads an open `review-redesign` request about the unit as a reason, "the architecture
  review: SAYS". It is not one of the routine reasons, so it sorts before units due only for their daily review.
- `resting` still applies: a unit resting is not taken, whatever the review said.
- When `modelling redesign` takes up a unit whose plan held a review request, it marks that request after the run:
  `proposed` with the change id, or `answered` with the result. The decided change then answers it through the
  existing `source == "redesign"` branch of `requests.sync`.
- It marks the request only if, re-read under the lock, its `review` stamp is the one the plan read. If a newer
  review re-raised it in between, the request is left open (lesson-1, lesson-2: equality on the stamp, never a time
  comparison).

*Cost and the daily cap (fails closed)*
- The review shares the redesigner's `daily` cap. Before the call, it checks
  `redesign.spent(p) + modeller.unsaid(prompt, model)["usd"] > daily`. If so, it does not call. It records an
  `architecture-reviewed` event with result `capped` (which does not count as a day's review) and says so on stderr.
- Before calling, it charges the estimate as a `redesign-ran` `call` event (`by: architecture-review`,
  `estimated: True`). After the call it charges the difference (real − estimate). So a run killed mid-call keeps
  the estimate charged.
- The call's cost is printed as a Claude Code result line (`_said`), so the run's cost is recorded
  (`costs/ai.py`). The `architecture-reviewed` event holds the model, the cost and the findings' ids.
- The redesign run that follows gets `budget=min(budget, daily - spent)` with spent re-read after the review.
- The call's time limit is `modeller.per_call(timeout, rounds + 1)`, so the review and the redesign's rounds fit
  the block's timeout.
- The docs say the bound is the estimated most (`modeller.unsaid`). They never say "never passes the cap", because
  `claude -p` takes no output limit (the finding that parked `modelreview`).

*The lock*
- The read-decide-write sequences hold an exclusive non-blocking `fcntl.flock` on `redesign.lock` in the project's
  state directory (the fixed file name, never built from input). The sequences are:
  - the review: is it due, the cap check, the call, writing the requests and the event;
  - marking the review request after a redesign.
- A second run that finds the lock held skips the review this run and says so.

**C. Docs.**
- SPEC §12e *Redesign*: the architecture section of the prompt, the daily review, its setting, its requests, its
  cap and its default model.
- The template's `redesign` parameter description.
- GAPS' Modelling entry: this part moved out of *Left*. Still left: a merge redesigned as one change, and the other
  architecture gaps.
- `docs/proposals/architecture.md`, *The ladder*: what is built.

**Not in it:**
- the redesigner's own pre-call cap check (`cost["usd"] >= budget` in `redesigner.run`): the parked
  `modelreview` gap's;
- a merge of two systems redesigned as one change set;
- any new page or panel: the review's findings show as requests on the Items tab and in the inbox.

## Files to touch

- `ergostat/numbers/archreview.py` (new: due, prompt, parse, hold, run)
- `ergostat/numbers/redesign_due.py` (`_in` for system refs; `triggers` reads `review-redesign`)
- `ergostat/numbers/redesigner.py` (`## Its architecture` in `prompt`)
- `ergostat/numbers/redesign.py` (`settings`: `review`)
- `ergostat/library/run/modelling.py` (`--review`; the review before `plan`; the lock; marking the review request)
- `ergostat/library/templates/modelling/template.yaml` (`review` default, description, `--review` in `run:`)
- `ergostat/library/templates/modelling/architect.md` (new: the review's guide)
- `tests/test_architecture_review.py` (new), `tests/test_redesign.py` (the prompt tests)
- `docs/SPEC.md`, `docs/GAPS.md`, `docs/proposals/architecture.md`

## Risks

- **lesson-1 (check, then write, without the lock):**
  - Two redesigner runs (an overlapping block run, a manual `modelling redesign`) both find the review due and both
    call.
  - Marking a review request answered after a redesign, when a newer review re-raised it meanwhile.
  - Held by the `flock` across due-check, cap check, call and write. The mark re-reads the request's `review` stamp
    inside the lock.
- **lesson-2 (wall time for order):** deciding that the redesign answered the review "after" it by comparing
  times. The mark compares the `review` event id for equality. "Due once a day" is a schedule over `DAILY`, not an
  ordering of records.
- **lesson-3 (fails open):**
  - A killed call that charges nothing: prevented by charging the estimate before the call.
  - `spent >= cap` checked before a call that costs more than is left: prevented by checking
    `spent + estimate > daily`.
  - An unreadable fit or failed `check` treated as "nothing wrong": the prompt says it could not be read.
  - An answer with no JSON taken as a day's clean review: it is recorded as `failed` (still the day's review, so not
    retried) and raises nothing.
- **lesson-4 (a limit with no ceiling):** findings per review (8), prompt size (40,000 characters, 60 systems),
  calls per review (1, no retry), reviews per day (1), all hard constants. The model name is the only setting, and
  an unpriced name is charged `unsaid`'s $1.0 fallback.
- **lesson-5 (stale state under a reused id):** `rid("redesign", "review-redesign", S)` is the same each day.
  Yesterday's `change` or `why` must not stick to today's finding, and yesterday's `review` stamp must not let
  today's redesign mark it.
- **lesson-6 (work after cancel):** the call runs through `subprocess.run(timeout=...)`, which kills the child on
  timeout. If the block's timeout kills the run, the estimate is already charged and the day's `started` review
  event is already written, so the next run neither re-calls nor charges nothing.
- **lesson-7 (two branches merged):** a new CLI flag on `modelling redesign` and a new `redesign:` key must still
  pass the template expansion tests and `check` on every example after merging origin/main.
- **lesson-8 (claims wider than the code):**
  - "fails closed" must be said as "its estimated most";
  - "never writes the model" needs a test;
  - "notes on other systems are not shown" needs a test.
- **lesson-9 (a test that can't fail):** each test below names the break that makes it fail.
- **lesson-10 (load flakes):** no sleeps. Every time is an injected `now`, and the call is an injected stand-in
  (`call=`).
- **lesson-11 (paths and ids from input):** the system names in the AI's answer become request ids and `about`.
  Taken only from the allowlist of the model's systems or units. The lock path is a fixed name under the state
  directory.
- **lesson-13 (stay inside the gap):** the redesigner's own `>=` budget check is not touched (parked
  `modelreview`). Unrelated suite failures are reported, not fixed.

## Acceptance tests

`tests/test_redesign.py`:
- `test_a_systems_own_architecture_notes_are_in_its_redesign_prompt`: a model with system `lab` whose parts split
  into two clusters and a wide interface. `prompt(..., "lab")` contains `system-splits@system.lab` and
  `interface@system.lab`. Another system's `interface@system.other` is not in it.
  - Fails if `_in` is left as it is (it fails on main today).
- `test_the_prompt_says_the_units_size_interface_and_subsystems`: the `## Its architecture` section names the
  size line, each interface port with its peers, and the subsystems. For `model`, each top system's size.
  - Fails if the section is dropped or the interface is taken from the wrong system.

`tests/test_architecture_review.py`:
- `test_the_review_holds_each_finding_as_a_request_and_writes_no_change`: a stand-in answer with a `redesign` on
  `lab`, a `split` on `big` and a `merge` on `a`. Gives one open `review-redesign` on `system.lab`, and two held for
  the owner. No `ergostat.model-change` is made, and the model files' bytes are unchanged.
  - Fails if `split` is held open, or if anything is written.
- `test_a_review_redesign_makes_its_system_due_first`: `next_due` with two units both due for their daily review
  and a `review-redesign` on the second. The second is chosen, and its `why` starts "the architecture review".
  - Fails if `triggers` does not read the request, or if the sort treats it as routine.
- `test_a_resting_system_is_not_taken_whatever_the_review_says`: a unit resting after a refused redesign with an
  unchanged signature stays skipped.
  - Fails if the review reason bypasses `resting`.
- `test_sync_does_not_answer_the_reviews_requests`: `requests.sync` leaves an open `review-redesign` open.
  - Fails if the source is anything but `redesign`.
- `test_the_review_runs_once_a_day_and_a_failed_call_counts`: a first run calls. A second at `now + 3600` does not.
  After a call returning `error`, a run at `now + 600` still does not call. At `now + DAILY + 1` it calls again.
  - Fails if "due" ignores failed reviews (retry storm) or the window.
- `test_the_review_is_not_called_when_its_estimated_most_would_pass_the_cap`: `spent` = daily − $0.01 and an
  estimate of $0.05. No call, an `architecture-reviewed` event with result `capped`, and the redesign run after it
  gets no budget.
  - Fails if the check is `spent >= daily`.
- `test_a_call_killed_mid_way_leaves_its_estimate_charged`: the stand-in call raises (it stands in for the run
  being killed). `redesign.spent` has risen by `unsaid`'s estimate. After a normal call, `spent` equals the real
  cost (the estimate plus the difference).
  - Fails if the charge comes only after the call.
- `test_the_answer_is_read_by_allowlist`: an unknown advice, a system not in the model (`../x`, `ergostat`, the
  template's own), a ninth finding and a duplicate unit are all dropped and said. Only allowlisted ids are made.
  - Fails if any unvalidated name reaches `rid`.
- `test_a_finding_made_again_the_next_day_clears_what_the_last_one_left`: day 1, `review-redesign` on `lab`. The
  redesign is proposed, then refused, and the request is answered. Day 2, the review says it again: the request is
  open with `change` None and `why` None, the new `says`, and the new `review` stamp.
  - Fails if `hold` does not write the update when the request is still open, or keeps the old `change`.
- `test_a_finding_not_said_again_is_let_go_but_one_waiting_on_its_change_is_kept`: day 2's review does not mention
  `lab` (open) or `ops` (proposed). `lab` is answered and `ops` stays proposed.
- `test_a_redesign_does_not_mark_a_request_a_newer_review_re_raised`: the mark step is monkeypatched to run a
  second review that re-raises the request between the plan's read and the mark. The request stays open with the
  new stamp.
  - Fails if the mark compares times or does not re-read.
- `test_a_second_run_holding_no_lock_skips_the_review`: with `redesign.lock` held by the test, `modelling redesign`
  makes no review call and says so. The planned redesign still goes ahead.
  - Fails if the lock is absent or blocking.
- `test_the_review_is_there_only_with_ai_and_off_turns_it_off`: the expanded template passes `--review sonnet` by
  default; with `review: off`, no review event. With `when: ask`, no review. Without `ai: true`, there is no
  redesigner block.
- `test_the_reviews_cost_is_printed_as_a_result_line_and_recorded_with_its_model`: stdout has the result line, and
  the event's data has `model: sonnet` and the cost.

Plus the four suites, rc 0, no page test skipped, with ruff clean. Origin/main is merged in and the suites run
again. `demo_check` runs on any example touched (none expected). The report says, for each test above, the break
that was made and that it failed.

## Size budget

450 net lines of code outside `tests/` and `docs/` (`architect.md` counted). Expected about 360:
- `archreview.py` ~190
- `redesign_due.py` ~25
- `redesigner.py` ~40
- `modelling.py` ~55
- `redesign.py` ~3
- `template.yaml` ~5
- `architect.md` ~40

## Notes from the plan review (answer each)

- Due-window rule contradicts itself: 'whatever that event's result' vs 'capped does not count'. State: every result except capped counts.
- Lesson-6 relies on a 'started' architecture-reviewed event that the definition never specifies. Write it inside the lock before the call, count it as the day's review, and extend test_a_call_killed_mid_way_leaves_its_estimate_charged to show a following run makes no call.
- Define the mark step when redesign.lock is held by another run's review: leave the request unmarked and say so; test it.
- test_a_redesign_does_not_mark_a_request_a_newer_review_re_raised must inject the competing review after the plan's stamp read and before the mark takes the lock. Injected inside the lock, the non-blocking flock makes it a no-op and the test cannot fail on the re-read.
- Add tests: _in is true for every ref when the unit is model, and a note on a subsystem appears in the parent system's prompt.
- Clamp min(budget, daily - spent) at 0 and assert the redesigner makes no call with it.
- SPEC must not carry the '(fails closed)' heading as a guarantee. Say the bound is the estimated most (modeller.unsaid).

## Where it stopped

Built, round 1: A, B and C as defined (346 net lines of code outside tests and docs, against 450). Nobody could be
asked, so these choices were taken, each the most reversible one:

- **`modelling redesign --review` defaults to `off`** when the flag is not given. The template passes
  `--review ${redesign.review|sonnet}`, so the template's default stays sonnet (and `redesign.settings` says
  sonnet). A run by hand, or an older caller, starts no larger-model call unless asked to.
- **The due window** (plan review): every `architecture-reviewed` result but `capped` counts as the day's review.
  `started` is written inside the lock before the call and counts, so a run killed mid-call is not called again
  that day. The killed-call test shows a following run makes no call.
- **An answer with no JSON line at all** is `failed` (lesson-3), and lets nothing go. An answer with JSON but no
  `{"review": ...}` line (the guide's `{"none": ...}`) is a review that found nothing, and lets go what it no longer
  says.
- **A `proposed` review request that is said again** is left as it is, waiting on its change (`hold(..., keep=)`).
  Reopening it would drop its link to the change that answers it.
- **The review's call charges** are `redesign-ran` `call` events under the system name `(architecture review)`,
  which no system can have. So an owner's ask is never read as taken up by them. Since they are `redesign-ran`
  events, "the first run" now ignores call-only events (`redesign_due._ever`).
- **The mark after a redesign** when `redesign.lock` is held by another run: it leaves the request unmarked and says
  so (`test_a_mark_under_another_runs_lock_leaves_the_request`). A failed redesigner call (`error`) leaves it open.
- **The budget clamp**: `max(0, min(budget, left))`. If what is left after the review is 0 or less, the run stops
  before planning, as the cap check before the review does. So a unit never rests for want of money.
- **The review's cap check** is against the whole `daily`, as defined (`redesign.spent + unsaid > daily`). It does
  not keep the model-reviewer's reserve (`reviewer.RESERVE`) the way the redesigner's `room()` does.

The plan review's notes are each answered above or in the tests: the due window; the `started` event; the mark
under a held lock; the competing review injected from `redesigner.run`, between the plan's stamp read and the
mark, outside the lock; `_in` for `model` and a subsystem's note in its parent's prompt
(`test_a_subsystems_note_is_in_its_parents_redesign_prompt`); the clamp, with the redesigner shown to make no
call; and SPEC giving the bound as the estimated most.

Not done here: origin/main could not be merged. The clone has no `origin` remote ref, and fetching would reach the
network. Local `main` is already in the branch. The whole unit suite and the four browser files were not run here
(the instructions leave them to the factory, under the watchdog). The test files touched and their neighbours were
run, and pass.

After the fast suites (round 1): the factory's `unit` run had one failure. Here, the whole unit suite with
`tests/test_architecture_review.py` left out failed once on
`tests/test_templates.py::test_a_trial_runs_a_copy_and_says_what_moved` ("nor its record": something wrote under the
test's `ERGOSTAT_HOME`). The factory's tail does not name the test it failed, so it may not be the same one. The
failing test passes alone, and passes in its own file under `-n 4`. A second run of the whole unit suite, this file
included, passed: 2515 passed, 69 skipped, 1 xfailed, rc 0. Nothing in this branch reaches that test. It runs a
`respond-to` template with no modelling block. The trial's child process has a home of its own (`author.trial`), and
`modelling redesign --review` defaults to `off` outside the template. So it is an intermittent leak between tests on
one xdist worker, unrelated to this gap (lesson-13): reported, not fixed here. No code was changed for it. A run of
the suite on a clean export of `main`, to compare, was refused here.

After the fast suites (round 1, second time): the factory's `unit` run again had one `F` (at 16%), and its tail
again stops before the failures list, so it does not name the test. No code was changed: there is no failure here
to fix, and a change made on a guess would not be a fix. What was run here, each passing:
- `tests/test_architecture_review.py`: 16 passed.
- Every test file that names redesign, modelling or the review (22 files, among them `test_redesign.py`,
  `test_templates.py`, `test_modelling_*`, `test_modelreview.py`, `test_cli_fallback.py`, `test_inbox.py`,
  `test_backlog.py`): 347 passed.
- The files that read the docs or the architecture (`test_spec_schema.py`, `test_parity.py`,
  `test_factory_knowledge.py`, `test_factory.py`, `test_daemon_yaml_review.py`, `test_architecture.py`,
  `test_diagram_rendering.py`, `test_blockdiagram.py`): 344 passed, 3 skipped.
- The files that check every example (`test_spec_compile.py`, `test_demo_check.py`, `test_chains.py`,
  `test_shards.py` and 10 more): 428 passed.

The whole unit suite (`scripts/suite_watch.py -- pytest -n 4 -rf`) was refused here, as was the earlier compare
run, so the failing test could not be found. Checked and ruled out as causes in this branch: the review's events are
stamped with the injected `now`, never the clock (so the once-a-day tests cannot drift under load); every new test
takes its own `ERGOSTAT_HOME` (conftest) and closes the locks it takes; `modelling redesign --review` defaults to
`off` outside the template, so no existing test starts a review call. Left: the factory's run with `-rf` (or the
log's failures section) to name the test. If it is one of this gap's, it is fixed in the next round. If not, it is
lesson-13's, reported.

Round 2: no review findings to answer. Main (07f9b250) was already merged in (5c74597f). The clone still has no
`origin`, so origin/main could not be fetched. No code was changed this round. What was run, now that main lets the
implementor run the suites under `scripts/suite_watch.py`:

- **The whole unit suite** (`suite_watch.py -- uv run python -m pytest -q -n 4 -rf`): rc 1, 2 failed, 2561 passed,
  69 skipped, 1 xfailed, in 26m52s (peak 412 threads, 1.06 GB). The two failures:
  - `tests/test_templates.py::test_a_trial_runs_a_copy_and_says_what_moved` ("nor its record": something wrote under
    the test's `ERGOSTAT_HOME`). This is the failure round 1 saw. It runs a `respond-to` trial with no modelling block,
    and nothing in this branch is on its path. The trial's child process gets a home of its own (`author.trial`).
    None of this branch's code starts a thread or a process that could outlive a test and write into a later test's
    home: the review's call is an injected stand-in in every test. It passes alone.
  - `tests/test_calls.py::test_the_socket_lists_items_as_the_command_does` (a `wait_for` on the socket ran out of
    time). It is in the calls socket, which this branch does not touch, and it passes alone.
  - Both together, and with `test_architecture_review.py` and `test_redesign.py`, under `-n 4` through suite_watch:
    80 passed, rc 0. Reported, not fixed (lesson-13). The suite was not run on main to compare: a second checkout of
    main could not be made here.
- **The four browser files** (the factory's `[suites] browser` command): rc 1, 7 failed, 236 passed, none skipped,
  in 22m45s (peak 548 threads, 3.99 GB). All 7 are in `test_diagram_rendering.py`:
  - three time limits: `test_every_view_draws_cleanly_and_in_time[big]` (3527 ms against 2500),
    `[image-squeeze]` (49900 ms against 20000), and `test_a_big_tangled_model_lays_out_in_time_and_cleanly`;
  - four click and drag checks: `test_every_part_opens_its_panel_when_clicked_even_mid_redraw`,
    `test_a_kinds_frame_dragged_in_the_process_view_takes_its_map_and_nodes_chosen_move_together`,
    `test_a_block_dragged_in_the_blocks_view_stays_pinned_its_lines_end_on_it_and_unpin_all_restores_it`,
    `test_every_lines_panel_links_to_the_parts_it_joins[coordinator]`.

  The 7 run alone under suite_watch: rc 0. This branch changes nothing in `ergostat/web`, the drawings or what they
  read (`git diff main...HEAD --stat`: `numbers/`, `library/run/modelling.py`, the modelling template, tests and
  docs). So they fail under `-n 4` load in this container. Reported, not fixed (lesson-13).
  - An earlier attempt at each suite was stopped by this session's 20-minute limit on a background command. The unit
    suite had no failure up to 94%, and the browser files were at 59%. They were run again, as above.
- **ruff** (`ergostat tests scripts`): clean. `test_spec_compile.py` and `test_demo_check.py`: 29 passed. No example
  is touched.
- **Each acceptance test, broken on purpose (lesson-9).** Each break was made by hand, the test was seen failing,
  and the code was put back (the tree is clean, and both files pass, 38 tests):
  - `test_a_systems_own_architecture_notes_are_in_its_redesign_prompt`: `_in`'s `system.` branch removed (as on
    main); also `_in`'s `model` case removed. Fails both times.
  - `test_a_subsystems_note_is_in_its_parents_redesign_prompt`: the `system.` branch removed. Fails.
  - `test_the_prompt_says_the_units_size_interface_and_subsystems`: the `## Its architecture` lines dropped; the
    interface taken from `other` instead of the unit. Fails both times.
  - `test_the_review_holds_each_finding_as_a_request_and_writes_no_change`: a split held `open`; the review writing
    an `ergostat.model-change.proposed` event; the review appending to the model file. Fails all three times. (A first
    try wrote a bare `ergostat.model-change` event, a type nothing writes, and the test passed. That is right: a real
    change is `ergostat.model-change.<state>`, which `proposals.stored` reads.)
  - `test_a_review_redesign_makes_its_system_due_first`: `triggers` not reading the request; the review's reason
    sorted as routine. Fails both times.
  - `test_a_resting_system_is_not_taken_whatever_the_review_says`: `next_due` skipping `resting` when a review asked.
    Fails. (Also fails with `triggers` not reading the request.)
  - `test_sync_does_not_answer_the_reviews_requests`: the requests held under source `review`. Fails.
  - `test_the_review_runs_once_a_day_and_a_failed_call_counts`: due counting only `reviewed`; a window of 60 s
    instead of `DAILY`. Fails both times.
  - `test_the_review_is_not_called_when_its_estimated_most_would_pass_the_cap`: the check as `spent >= daily`; the
    budget clamp removed (`budget=a.budget`). Fails both times.
  - `test_a_call_killed_mid_way_leaves_its_estimate_charged`: the estimate charged only after the call; the
    `started` event not written before it; due counting only `reviewed`. Fails all three times.
  - `test_the_answer_is_read_by_allowlist`: the allowlist replaced by "any non-empty name"; the 8-finding limit
    removed. Fails both times.
  - `test_a_finding_made_again_the_next_day_clears_what_the_last_one_left`: `hold` not writing again when the request
    is open (`new` dropped); the `change: None` reset dropped. Fails both times.
  - `test_a_finding_not_said_again_is_let_go_but_one_waiting_on_its_change_is_kept`: nothing let go; a `proposed`
    request let go too. Fails both times.
  - `test_a_redesign_does_not_mark_a_request_a_newer_review_re_raised`: the stamp's equality check dropped from
    `mark`. Fails. (`test_a_redesign_marks_the_request_it_took_up` still passes then, as it should.) Also fails with
    `hold`'s `new` dropped.
  - `test_a_second_run_holding_no_lock_skips_the_review`: the `flock` call removed. Fails. A blocking `flock` was
    not tried: the test would hang, and neither `timeout` nor pytest-timeout could be used here to bound it.
  - `test_a_mark_under_another_runs_lock_leaves_the_request`: the mark ignoring the held lock; the `flock` removed.
    Fails both times.
  - `test_the_review_is_there_only_with_ai_and_off_turns_it_off`: `review: off` not honoured; `when: ask` running
    the review. Fails both times.
  - `test_the_reviews_cost_is_printed_as_a_result_line_and_recorded_with_its_model`: no result line
    (`on_call=None`); the model left out of the event. Fails both times.

Left: the unit suite and the browser files rc 0 on the factory's run. Every failure seen here passes alone and is
outside the gap.
- Refused here: `timeout 90 uv run python -m pytest ...`; `ps -A -o command=`; a shell write to `/tmp`; the Write
  tool outside `/work`.
- So the breaks were made with Edit on the source and put back by hand. No scratch file was written.

Round 3: answering the three blocking findings. 24 net lines of code were added (about 370 in total, against 450).

- **`review: off` unquoted.** The finding's premise does not hold here. The model's loader (`spec/load.py:116`) and
  the template's (`library/templates.py:72`) take only `true` and `false` as booleans (YAML 1.2), so an unquoted
  `off` stays the string `off`, and `--review off` is rendered. The test now loads the unquoted form and shows that no
  review runs. A written `review: false` would render `--review false`, so it is mapped to `off` too, in
  `_model_name` and `redesign.settings`, and `--review true` is refused. Tested in
  `test_the_review_is_there_only_with_ai_and_off_turns_it_off`. Break: the `false` mapping dropped. Fails.
- **The cap check, the reviewer's reserve and the lock.** The review now checks its estimated most against
  `redesign.room` (new: the redesigner's `room()` moved there, which the block's `room` now calls). That is what is
  left of the cap, never the quarter kept for the reviewer. The check, the `started` event and the estimate's charge
  are made under `proposals.lock`, the lock `redesign.held` takes. The reviewer's `held` check waits on it, and it
  reads the review's charge (a `redesign-ran` event, which `spent` counts) once it gets the lock. The charge is
  the definition's `redesign-ran` `call` event, not a `held` record. A `held` record is released after the call, so
  using both would charge the estimate twice. The cap test no longer sets `RESERVE` to 0. It shows a review capped
  with $0.51 of the cap unspent but $0.01 of it the block's. Break: the check against `daily - spent`. Fails.
  New test: `test_the_reviews_cap_check_sees_a_reviewer_hold_and_is_made_under_the_holds_lock` covers a reviewer
  hold in place, a reviewer hold made in the gap between the estimate and the check, and the charge made with
  `proposals.lock` held. Break: the check under another lock file. Fails.
- **The timeout.** After a review that called, the redesigner is given `timeout × rounds / (rounds + 1)`
  (`archreview.timeouts`), so each of its rounds' calls gets `per_call(T, rounds + 1)`, as the review's call does.
  Their limits sum to `0.8 T`, the room `per_call` keeps on a day with no review. On a day with no review call
  (done today, capped, lock held), the rounds get the whole timeout. SPEC says this, and no longer says the review
  and rounds "fit the block's timeout". New test: `test_the_review_and_the_rounds_share_the_blocks_timeout` (1 and
  3 rounds, 900 s and 3000 s, and a day with no review). Break: the redesigner given the whole timeout. Fails.

Run this round, one file at a time: `test_architecture_review.py` (18 passed); `test_redesign.py` with
`test_modelreview.py` (43); `test_templates.py`, the `test_modelling_*` files, `test_redesign_memory.py`,
`test_cli_fallback.py`, `test_spec_compile.py` and `test_demo_check.py` (149); `test_spec_schema.py`,
`test_parity.py`, `test_redesign_bench.py` and `test_architecture.py` (59). ruff is clean. The clone still has no
`origin`, so origin/main was not fetched. The whole unit suite and the browser files are left to the factory's run.
A shell loop over the test files and a combined ruff-plus-`git diff --numstat` command were refused. Each was run
again as a single command.
