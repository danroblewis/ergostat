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
