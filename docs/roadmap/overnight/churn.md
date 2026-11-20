# churn: proposals that persist, identifications that are honest

Branch `churn`, from main at 214d864. The owner's report (ticket-factory, after adding 130 tickets at once): every
modelling proposal ends "superseded" ("let go: found again otherwise, or no longer found"), among them a loop-process
identification for `reviews-answered` that follows 2% of the record held out, whose errors are not white and not
independent of u, identified in closed loop. The projections are far off, and did not adjust. Part of the GAPS entry
*Proposals superseded by any edit* (rebase instead of supersede).

## Definition of done

1. **Churn.** A change ergostat's own finders make (a parameter estimate, an equation, a structural change, a loop's
   process or gain) is identified by **what it is about**: its kind, how it was found, the parts it is about and those
   parts as the model has them now, never its numbers. Found again with new numbers, the same item is **revised in
   place** (an `ergostat.model-change.revised` event with the new numbers and evidence, and a `revisions` count),
   keeping its history and any judging; one under test or passed is left to the judge. It is superseded only when its
   subject no longer applies (a part it is about was removed or changed by an edit, said so), when its finder no longer
   finds it, or when it was decided. A change of the model elsewhere carries it to the new version instead. The
   estimator no longer lets go of changes it did not make (a loop's process, a structural change).
2. **A quality floor.** A process identification is not proposed when it follows less held out than half of what the
   record's jitter allows (at most 50%), or its errors held out are not white, or not independent of u. Instead the goal
   gets the finding **`loop-not-identifiable`** saying what the record lacks and what would identify it: a step test
   (offered where one can be), a large outside change in its input (a burst of arrivals), or more hours of record. A
   parameter estimate with no support on the record held out (its error held out not lower) is not proposed.
3. **Exogenous steps.** Large changes in a loop's measured inputs beside the path and in what arrives at its goal's
   stock (a burst, like the owner's 130 tickets) are found, and the process identified from the window around each,
   with that input fitted beside u; it is said "identified around an outside step at T". Validated on a synthetic
   closed-loop record with a known process and a burst: closer to the truth than identification from the loop working.
4. **Projections honest about fit.** Where a projection's charted stocks fit worse than their mean (skill < 0), or the
   loop on its goal could not be identified, the strip says so in front ("Low confidence: ...") and draws a wider band
   (the fan widened, or the replay's own error about the projection), as the impact report leads with its confidence.
5. **Docs.** SPEC §12d and §12e, the agent guide (a loop that is not identifiable: offer a step test; projections far
   off after a burst: suspect missing structure such as capacity, and ask for a redesign), GAPS (what of *rebase
   instead of supersede* is done).

## Acceptance tests

- `tests/test_churn.py::test_a_proposal_found_again_with_new_numbers_keeps_its_id_and_history`
- `tests/test_churn.py::test_superseded_only_when_its_subject_goes`
- `tests/test_churn.py::test_the_estimator_does_not_let_go_of_a_loops_process`
- `tests/test_churn.py::test_a_poor_identification_gives_the_finding_not_a_proposal`
- `tests/test_churn.py::test_identification_around_an_outside_step_beats_the_loop_working`
- `tests/test_churn.py::test_the_strip_says_low_confidence_in_front_and_widens_the_band`
- `tests/test_churn.py::test_the_owners_case_proposals_persist_and_get_judged` (a ticket-factory-like record, a burst
  of 130 arrivals; before: every proposal superseded; after: kept, revised and judged)
- the unit and browser suites under `scripts/suite_watch.py`, rc 0, no page test skipped; ruff; `demo_check` on
  ticket-factory and image-squeeze.

## Size budget

400 net non-test lines (outside `tests/` and `docs/`).
