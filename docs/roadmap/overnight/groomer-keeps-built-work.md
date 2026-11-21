# groomer-keeps-built-work: the groomer never splits a gap that already has built work

depends-on: []

On 2026-11-21 the groomer proposed splitting `operating-states-continued` into three new gaps. It continues a branch with 22 commits and 1,623 lines; the new children would start from main and abandon that work. The coordinator removed the split by hand.

## Definition of done
`backlog.py`'s check refuses a split of a gap that has `continues`, or whose branch in the drop has commits main lacks, and says why. The groomer's prompt says so. The rest of a proposal still applies.

## Files to touch
`dev/bin/backlog.py`, `dev/prompts/groomer.md`, `tests/test_backlog.py`.

## Risks
- lesson-3: a branch that cannot be read counts as having work.

## Acceptance tests
- `tests/test_backlog.py::test_a_split_of_a_continued_gap_is_refused`
- `tests/test_backlog.py::test_a_split_of_a_gap_with_commits_is_refused`
- `tests/test_backlog.py::test_a_split_of_an_unbuilt_gap_still_applies`

## Size budget
25 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. Choices made alone (the most reversible):
- `backlog.built` reads the drop through `agents.drop` (which makes it, or brings its main up to date, as the intake
  does), not a new reader. No branch in a readable drop means no work. Anything that fails (the drop, its main,
  `rev-list`) counts as work, and the split is refused with the error (lesson-3).
- A ref that names a missing object looks the same as no branch to `rev-parse --verify`. Such a ref holds no work
  that could be reached, so the split goes ahead.
- The groomer's context now shows a gap's `continues` too (one word), so the prompt's rule can be followed.

Size: dev/bin/backlog.py +28/-4 (24 net, with its docstring), dev/prompts/groomer.md +3/-1.
Not run here: the unit suite and the four browser files (the factory runs them under the watchdog). There is no
origin/main in this clone and the network is off, so main was not merged in again; the branch is on local main.
