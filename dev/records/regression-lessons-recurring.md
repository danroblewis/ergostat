# regression-lessons-recurring: A lesson's class found again after a brief carried it is counted, and held low

depends-on: [regression-guarantees-model]

## Problem

`first-pass-with-lessons` compares yields (dev/model/knowledge.yaml:74-79). Nothing counts a review finding of a class the gap's own brief carried, which is the lesson failing as a guarantee (proposal section 3, F12 row; section 4, `lessons-recurring`). The data exists. The librarian records each review's classes (`review.measured: classes`, dev/bin/librarian.py:1-11), and each brief records the ids it carried (`knowledge`, dev/bin/knowledge.py:264-272).

## Change

- `measure.py lessons-recurring` (in `knowledge_reading`, dev/bin/measure.py:291-311): over reviews written in the last 14 days, the count of classes found that are in the reviewed gap's first brief's carried lesson ids. A review with no recorded classes is left out and counted on stderr. No reviews in the window gives no value.
- dev/model/guarantees-lessons.yaml: auxiliary `lessons-recurring`, goal `lessons-hold`: `<= 2`, `on-stale: "off"`, the setpoint a parameter. It is unserved until regression-guarantees-wired. Its loop goes to the librarian there.

## Definition of done

1. A finding of a carried class counts. One of a class not carried does not.
2. A review with no classes is left out and said.
3. No reviews gives no value.
4. `ergostat check`: no errors.

## Files to touch

dev/bin/measure.py, dev/model/guarantees-lessons.yaml (new), tests/test_factory_knowledge.py.

## Acceptance tests

- `test_a_carried_class_found_again_counts`
- `test_a_class_not_carried_does_not_count`
- `test_no_reviews_has_no_value`

## Size budget

40 net lines outside tests/.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1 (2026-11-23). Choices made with no one to ask, each the most reversible:

- **The setpoint is the literal `<= 2`, not a `parameters:` entry.** A goal's `hold` is a setpoint and only a number
  is accepted there (`SETPOINT` in ergostat/spec/ir.py:16). A parameter nothing could reference would be dead. The
  number is marked in the YAML as the value to tune. If the owner wants a real parameter, ergostat has to accept a
  setpoint reference first, and that is outside this gap.
- **"No recorded classes" means the field is missing**, so the librarian has not measured the review. An empty list
  means it was measured and found nothing, and that counts as 0.
- **A review whose gap has no first implementor brief recorded is left out and said too.** It is not taken as
  "carried nothing", so a missing brief never reads as a held lesson (lesson-3). If every review in the window is
  left out, there is no value (exit 1), never 0.
- **Every round's review is counted**, against the first implementor brief only, as the Change says. Only
  `lesson-*` ids count: the librarian's `new-*` classes are never carried.
- dev/README.md *Regression guarantees* has one more bullet for the goal. It is not in "Files to touch", but the
  section was written for later gaps to extend.
- `ergostat check` as a shell command was refused in this session. Done item 4 is checked by
  `test_a_carried_class_found_again_counts`, which loads ergostat.yaml with `ergostat.spec.read` and asserts no error.
  It also asserts the goal and the auxiliary's sensor. `lessons-hold` is missing feedback (a warning) until
  regression-guarantees-wired.

Tests broken on purpose and seen to fail: dropping the carried intersection, reading the last brief instead of the
first, counting an unmeasured review as 0, and giving 0 with no reviews.

**After `ergostat check` sent the branch back** (`auxiliary-without-causes auxiliary.lessons-recurring`,
`missing-feedback goal.lessons-hold`). The note above about missing feedback lasting until regression-guarantees-wired
no longer holds. The definition has no `allows-findings` line, and that line was not added.
- `lessons-recurring` is `driven-by: [-stock.knowledge-entries]`: carried knowledge, sharpened by the librarian's
  applied shapes, is what should bring the count down. Its value is still only its sensor's.
- `lessons-relearn`, an `external` block (`in: goal.lessons-hold.off`, `out: block.librarian`), closes the loop the
  long way: through lessons-found, lessons-approved and lessons-added to knowledge-entries. This is the most reversible
  choice. ergostat never runs an external block, and the librarian starts only on `review.written` (`due()` returns
  early for `on:` blocks, ergostat/spec/engine.py:752), so nothing changes at run time. Wiring the real loop is still
  regression-guarantees-wired's job, and that gap can replace or drop this block. The librarian's own entry in
  knowledge.yaml was not touched.
- `test_a_carried_class_found_again_counts` now asserts that the model has no findings about the goal, the auxiliary,
  the new block or the librarian, and that the loop closes. It was run before the model change and failed with both
  findings.

**Round 2 (2026-11-23): main (2f08c24e) merged.** The one conflict, dev/README.md *Regression guarantees*, kept
main's `quarantine-small` bullet and the branch's `lessons-hold` bullet after it. The lessons-hold bullet's last
sentence ("Nothing serves it yet (missing feedback)") was stale after round 1. It now names the `lessons-relearn`
external block. After the merge, tests/test_factory_knowledge.py passed (106) and ruff was clean. The code did not
change.

**Round 2, recheck (2026-11-23).** The queue's finding "conflicts with main: dev/README.md" was answered by the merge
above. Local `main` (2f08c24e) is an ancestor of HEAD, dev/README.md has no conflict markers, and the branch's only
change there is the `lessons-hold` bullet, which comes after main's `quarantine-small` bullet and splices into no
other entry. tests/test_factory_knowledge.py passed again (106) and ruff is clean. `uv run ergostat check` was refused
in this session as well. Done item 4 still rests on the model check inside `test_a_carried_class_found_again_counts`.
If the queue's main has moved past 2f08c24e, it has to be merged again. That main is not in this clone.
