# the-job-person-steps-and-laws: what only I can do is marked as mine, and the preparers' capacity has a designed law
depends-on: [the-job-equations-ops]

## Definition of done
- Person steps marked: every flow that only the owner moves (post, approve, reject, declare, dismiss, send, present) is the `out` of a `type: person` block on agent `me`, and no program or AI block has such a flow as an output. The set is written once in the model (the flows' descriptions say "mine") and the test reads it from the model, not from a list in the test.
- A designed law: the preparers' capacity is a setting stepped by a program block in integral form (u_k = u_(k−1) + gain × e_k) on the drafting backlog's error, with `gain`, `deadband`, `resolution` and `limits` declared in the YAML and read from `params` (no constant held in `bin/`). The preparer blocks' `pool` reads that setting with a hard `most`.
- A missing or unreadable backlog reading moves nothing (no step), and the setting never leaves `limits`.
- `COORD`-style switch: `JOB_POLICY=off` keeps the setting fixed, so the law can be compared off and on.
- check stays clean (the first sub-gap's test still passes); the new loop comes out balancing.

## Relation to other work
- the-job-equations-ops: builds on its clean model and its test file.
- gap/forward-pass-levelled-by-block-capacity: reads blocks' pools; this only sets a pool from a stock, the form already on main.

## Files to touch
- `examples/the-job/job/*.yaml` (the domains with person blocks, and the new capacity stock, goal and block in `rhythm.yaml`)
- `examples/the-job/bin/job.py`
- `examples/the-job/README.md`
- `tests/test_the_job_model.py` (new)

## Risks
- lesson-3: an unread backlog stepped as zero error, or as the worst case pushing capacity up; it must not step.
- lesson-4: the setting multiplies preparer runs; `limits` and the pool's `most` are the ceiling, checked at run time too.
- lesson-9: a person-step test that reads a hard-coded list passes when a new flow is moved by a preparer.

## Acceptance tests
- `tests/test_the_job_model.py::test_only_person_blocks_move_my_steps`: every flow marked mine is moved by a person block on `me` and by nothing else; fails when a preparer's `out` is pointed at `comments-posted`.
- `tests/test_the_job_model.py::test_the_capacity_law_steps_by_gain_within_deadband_and_limits`: runs the block's program with `params` and errors around the deadband and past the limits; the step is gain × error, none inside the deadband, clamped at the limits.
- `tests/test_the_job_model.py::test_the_capacity_law_does_not_step_on_a_missing_reading`: no reading (or NaN) leaves the setting unchanged.
- `tests/test_the_job_model.py::test_the_capacity_loop_is_balancing`: the loop through the setting, the pool and the backlog is balancing.

## Size budget
150 net lines
size: M (confidence: low)

## Notes from the plan review (answer each)

- 'the drafting backlog' and 'the preparer blocks' are not named. Preparers with `pool: 2` sit in nine domains (awareness.yaml:130, delivery.yaml:110, documents.yaml:89, incidents.yaml:217/244, safety.yaml:184/202, stewardship.yaml:83, support.yaml:84, team.yaml:81/90), each draining its own backlog (incidents `alerts-to-draft`, documents `drafting`, team `update-drafting`). One integral law needs one error: name the goal it reads (one domain's, e.g. incidents' every-alert-drafted, or a new auxiliary summing the to-draft stocks in rhythm.yaml) and list exactly which blocks' `pool` read the setting. Otherwise the implementor guesses and the loop's polarity and gain are undefined.
- test_the_capacity_loop_is_balancing has nothing real to check. A pool's stock is not a causal link: SPEC.md:2875 says it 'is not one of the block's reads', and ir.py:728 keeps pool_now apart from the block's in/out, so ergostat's loop finding will not see setting -> pool -> drafting flow -> backlog -> law. Either declare the link in the model so ergostat itself finds the loop (e.g. the drafting flow `driven-by: +stock.<setting>`, or the setting in the preparer's `in:`), and have the test read the loop and its polarity from ergostat; or narrow the done item. A test that writes down the loop's signs itself always passes.
- / [lesson-3] The plan does not say how the setting is stored or read. `pool: {now: ...}` needs a stock with a sensor (else `pool-unmeasured`, SPEC.md:2855), and a goal, as in the coordinator's quality-integrator, cannot be a pool's source. So the program must step a flow into a stock that has a sensor (and a start value). And SPEC.md:2855 makes an unread or non-number setting a pool of 0: every preparer stops. The definition covers only a missing backlog reading. Say what the setting reads before its first step and after a lost reading, and test that the preparers keep taking work (the start value or the lower limit) rather than stopping.
- Check that limits[1] <= the pool's `most` and that limits[0] >= 1, in the test or by check. A setting allowed above `most` is silently cut, and a lower limit of 0 stops the preparers.
- Reading 'mine' from descriptions: stock descriptions already say it ('a pull request of mine', delivery.yaml:10; messages.yaml:21). Read only flows, with one exact marker (e.g. a description ending '(mine)'), and break it as the plan says (point a preparer's out at comments-posted) and also by removing the marker from one flow, so the test fails when the set shrinks.
- Most person blocks are already in the domain files (e.g. incidents.yaml:220-237: post-alert-comments, declare-incident). Expect this part to be marking flows and the test, not moving blocks; say so in the report so the size isn't spent there.
- JOB_POLICY=off must reach the program through the engine's environment. Show the off path writing no step (not stepping by 0, which still prints a move), so the off-and-on comparison in the-job-structure-and-behaviour-tests reads a fixed setting.
- The step test should also round to `resolution` and show a step that rounds to 0 is not printed. The plan declares resolution but none of the tests check it.

## Where it stopped

Built, round 1. Every done item is in the code and its four acceptance tests pass; demo_check and the browser files
were not run here (see the end).

**The plan review's notes, each answered:**

- *Which backlog, which blocks.* The error is a new goal in rhythm.yaml, `alert-drafting-paced`, on incidents'
  `alerts-to-draft`, held `== 1` with `tolerance: 2` (off at four waiting, holding again at two or fewer, so it stays
  off the morning brief in ordinary bursts). Exactly one block's pool reads the setting: `alert-companion`
  (incidents.yaml, `pool: {now: stock.drafting-capacity, most: 3}`). The other preparers keep `pool: 2`. One error
  can only steer the blocks that drain it, and no sensor can sum the other domains' backlogs without a new program
  sensor. This is the most reversible choice: another domain's preparer joins by pointing its pool at the stock and
  its drafting flow's `driven-by` at it. The goal is two-sided because a `<=` goal's error is never above 0 (ir.py
  `Setpoint.error`), and a law on it could only ratchet capacity up.
- *A loop ergostat can see.* `comment-drafting` is `driven-by: +stock.drafting-capacity`, so `causal.loops` finds the
  loop capacity-law → capacity-steps → drafting-capacity → comment-drafting → alerts-to-draft → alert-drafting-paced
  → capacity-law, and the test reads its parts and polarity from ergostat. I found that ergostat's B can't fail here:
  it signs a machine block's reading of its error as whatever closes the gap (causal.py `_CLOSES`), so a link written
  `-stock.drafting-capacity` still came out B. The test therefore also signs the loop again with the law's real sign
  at that link (the gain's), every other link as ergostat has it. With the link flipped, that check failed (seen).
- *How the setting is stored and read (lesson-3).* The law writes `run/capacity.json`. The stock's sensor is
  `python3 bin/capacity.py read 2`: it prints what is stored, or the start value 2 when nothing is stored or what is
  stored can't be read (tested: no file, and a corrupt file, both read 2, never 0). The law steps from that same
  value. ergostat itself still makes a pool whose stock has no reading at all (the sensor's process failing) a pool
  of 0, which is SPEC §9.5 and outside this gap.
- *limits within `most`, lower limit ≥ 1.* Tested: `limits: [1, 3]`, the pool's `most` 3, the start value 2 within
  them and the same on the law's and the sensor's command lines.
- *The `(mine)` marker.* It is read from flows only, as a description ending `(mine)`. The test checks both
  directions (a flow marked mine is moved only by a person block on `me`; a flow such a block moves is marked mine)
  and breaks the model both ways in copies: a preparer's out pointed at `comments-posted`, and the marker removed from
  `ramps-approved`. Each break is found. Eleven flows are marked: comments-posted, outages-declared, outages-dismissed,
  ramps-approved, ramps-rejected, docs-approved (present), reviews-answered, mentions-answered, tickets-answered,
  reviewed-after-nudge (send) and messages-routed-by-hand.
- *Person blocks already there.* None was moved or added. This part was marking flows and the test. The weekly
  update has no `sent` flow and no person block (team.yaml), and none was added (build only what was asked).
- *JOB_POLICY=off.* The engine passes its environment to the program (engine.py: `env = {**os.environ, ...}`). When
  off, the law prints nothing and writes nothing. The test runs it off (no output, the setting still 2) and on (a
  step of 1).
- *Rounding to `resolution`.* Tested: with gain −0.4, an error of −1 (0.4) rounds to no step and prints nothing, and
  −2 (0.8) rounds to a step of 1.

**Also:** a stale error reading (`stale` in the run's input), a non-number, NaN, a bool, or no input all step
nothing. Missing law params step nothing too.

**Beyond the Files list:**
- The law is a module of its own, `bin/capacity.py`, not `bin/job.py`. job.py imports the simulated world, which the
  law does not need, and the tests run the law from a copy of the one file. job.py is unchanged.
- `tests/test_blockdiagram.py::test_the_blocks_panels_use_control_words_only` failed once the-job (an example it
  scans) had a pool read from a stock. The Blocks panel's pool row says `(stock.drafting-capacity)` as SPEC §9.5
  writes it (`2 now, at most 4 (stock.NAME)`, pinned by test_pool_now.py:427), and that test bans the word "stock".
  So two of ergostat's own rules disagree, and no example had shown it before. I took the most reversible fix: the
  test now strips the pool's own `(stock.NAME)` text, the way it already strips the model's descriptions. Nothing
  else is exempted, and ergostat's code and SPEC are unchanged. If the owner would rather the row drop the word
  (code, SPEC, test_pool_now), that is its own gap.

**Breaks seen to fail the tests (lesson-9):** each of these, with the code restored after:
- the deadband check loosened (`<` for `<=`);
- the upper clamp removed;
- the rounding removed;
- a missing input treated as an error of −1;
- the stale check removed;
- the off path printing a move of 0;
- the `driven-by` removed (no loop found);
- the `driven-by` sign flipped.

**Run here:**
- tests/test_the_job_model.py (6 passed);
- the control-words test above;
- these unit files, which load the-job, all passing: test_coherence, test_blockdiagram, test_inbox, test_architecture,
  test_extremes_closed, test_item_systems, test_finished_states, test_scale_caches, test_sd_tools, test_spec_systems,
  test_numbers, test_templates, test_graph_cli_web, test_modelling_template, test_pool_now, test_dynamics_view,
  test_counts, test_chains, test_observer, test_modelling_core, test_template_exports, test_incremental,
  test_changesets and test_cloud_arrivals;
- `ruff check ergostat tests scripts`, clean.

**Not run here:**
- `scripts/demo_check.py the-job`: the command was refused in this container.
- The four browser files and the whole unit suite, which are the factory's and the merge queue's to run.
- The off-and-on behaviour comparison, which is the-job-structure-and-behaviour-tests'.
