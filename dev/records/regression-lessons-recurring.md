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
