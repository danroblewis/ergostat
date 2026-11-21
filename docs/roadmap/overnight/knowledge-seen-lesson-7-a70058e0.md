# knowledge-seen-lesson-7-a70058e0: lesson-7 seen as a new shape

depends-on: []

Branch `knowledge-seen-lesson-7-a70058e0`, from main. Asked by the librarian, approved by the coordinator.

## Definition of done

`dev/knowledge/review-lessons.md`: lesson-7 seen as a new shape, as below, and nothing else changed.

Add to its "Seen as:" (a new line under its first paragraph if it has none), in its style: the branch is called built while the unit suite, the four browser files and test_repair2 were never run on the host, and the end-to-end tests that cover the changed stderr path are skipped

From:

> docs/roadmap/overnight/repair-runlog.md (Where it stopped: 'Not run by the implementor: the whole unit suite and the four browser files'; 'test_repair2.py skips here') vs the definition of done and the house rules (lesson-7, lesson-9; raised in the previous review and not fixed): the branch changes what capture.failed receives (only the last TAIL characters of the run's own file, not the whole run output from the block log), and the only end-to-end tests that push a real traceback through run_block into triage (tests/test_repair2.py:173, :285) have still never run against it. The whole unit suite, the four browser files and test_repair2 on a host with the OS sandbox must run with rc 0, and the results must be recorded.

## Acceptance tests

- `tests/test_factory_knowledge.py::test_knowledge_files_parse`: the knowledge files still parse into entries with ids.

## Size budget

0 net lines of code (knowledge only).

## Where it stopped

Built, round 1. Lesson 7 had no "Seen as:", so one was added under its first paragraph, wrapped at 120 like the rest
of the file. The wording was put in the file's style (a past-tense noun phrase ending in a period, like the other
"Seen as:" entries): "the branch called built ... were skipped" for "the branch is called built ... are skipped";
otherwise the words are as given. This is the easily reversed choice. Nothing else changed.
`tests/test_factory_knowledge.py`: 22 passed; ruff clean. This clone has no `origin/main` ref, so origin/main could
not be merged in here (lesson-7); the factory's merge queue runs the suites on the merged tree. The implementor did
not run the unit suite or the four browser files, because this is a knowledge-only change and the factory runs them
afterwards.

After the fast suites: `unit` failed on one test, `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth`
(1 failed, 1902 passed, 69 skipped). It failed at :434: after `second.close()`, one ticket's lease still had a holder.
That means a lease was taken while the engine was closing and never given back as "stopped with ergostat"
(`ergostat/leases/dispatch.py` `finish`). This branch changes only two markdown files (`git diff main --stat`), and
nothing in the lease, engine or runner code reads them, so the failure is unrelated (lesson-13). It looks like a
load-dependent race between close and a dispatch that has just started (lesson-10), and should go in a gap of its own.
It is not fixed here because the definition says "nothing else changed" and allows 0 lines of code. The factory asked
for a code fix; the more reversible choice is to leave the code alone and report the failure. The implementor could
not re-run the test alone to see whether it is a flake: shell commands were refused in this session.

After the fast suites, second time: `unit` failed on a different lease test,
`tests/test_leases.py::test_a_lease_held_by_a_run_survives_a_model_edit` (1 failed, 1902 passed, 69 skipped), at :532:
`swap` reported `runs == []` while the item was already `leased`. The code shows a window that explains it:
`ergostat/leases/dispatch.py` `take` writes the lease event (:204), which makes the fold say `leased`, then re-reads the
fold and records resources, and only then adds `"worker ticket/1"` to `engine.running` and pins the model (:218-220).
The test waits for `leased` and then swaps. Under load the swap can land in that window, so the run is not carried
over, and it is then pinned to the *new* model. That is a real race in ergostat (lesson-10), not a test timing
problem. The likely fix is to add the run to `running` and pin the model under the engine lock before or with the
lease event, and drop it again if the fold refuses the take. It is not fixed here. This branch changes only two
markdown files, nothing in the lease or engine code reads them, the definition allows 0 lines of code and says
"nothing else changed", and lesson-13 says an unrelated failure goes in a gap of its own. The factory asked for a code
fix; leaving the code alone and reporting is the more reversible choice. The two lease failures so far (close, then
swap) both come from dispatch's take/finish lifecycle and probably belong in one gap. The implementor could not re-run
the test alone or commit this section: shell commands were refused in this session, so it is left uncommitted.
