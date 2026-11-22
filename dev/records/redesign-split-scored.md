# redesign-split-scored: the scorecard scores how a change set splits parts into systems
depends-on: []

## Definition of done
- The redesign scorecard (`ergostat/numbers/scorecard.py`) has a measure of systems, before and after. For each system
  it counts the flows and causal links whose two ends are in it, and the links that cross from it to a part in another
  system. Parts are placed by the existing system-of-a-part rule.
- Some changes add a system or move parts between systems. If, after the change, any system it made or changed has
  more crossing links than inside links, the measure is worse, and the verdict cannot be "better". The scorecard's
  "why" names that system. If every such system has more inside links than crossing links, the measure counts as
  improved.
- A change that adds no system and moves no part between systems gets no system measure, and its verdict is
  unchanged. All existing scorecard tests still pass unchanged.
- A renamed part is counted under its new name: a rename alone never changes the measure.
- The measure appears in the scorecard's printed lines and on the review entry, the same way the other measures do.
- The redesigner guide (`redesigner.md`), SPEC §12e's scorecard table, `docs/proposals/redesign.md` and the GAPS
  entry's Open clause say that a split is now scored.

## Relation to other work
- architecture-per-system-redesign (merged): builds on it. Its review raises split requests, and this scores the
  change set that answers one.
- redesign-rescored-as-the-record-moves (merged): no change to rescoring. The new measure is worked out like the
  others each time the change is scored.

## Files to touch
- `ergostat/numbers/scorecard.py`
- `ergostat/library/templates/modelling/redesigner.md`
- `docs/SPEC.md`
- `docs/proposals/redesign.md`
- `docs/GAPS.md`
- `tests/test_redesign.py`

## Risks
- lesson-3: a part whose system can't be found could be counted as inside every system, which makes a bad split look
  cohesive. Such a part must count as crossing.
- lesson-8: the docs could say "a split is judged" when only how connected the new systems are is measured. The docs
  must say exactly that: links inside against links across, nothing about purpose.
- lesson-9: a test whose split is built so it passes whatever the verdict rule says. Each verdict needs a case that
  goes the other way.

## Acceptance tests
- `tests/test_redesign.py::test_a_cohesive_split_scores_the_systems_measure_improved`: a change set that splits one
  system into two, each mostly linked inside itself, scores improved and keeps "better" when the other measures are.
- `tests/test_redesign.py::test_a_split_whose_system_crosses_more_than_it_holds_is_not_better`: the same model split
  badly. The verdict is not "better", and "why" names the system.
- `tests/test_redesign.py::test_a_rename_only_change_has_no_systems_measure`: renames and in-system edits leave the
  measure out and the verdict as before.
- `tests/test_redesign.py::test_a_part_of_no_found_system_counts_as_crossing`: the fail-closed case.

## Size budget
90 net lines
size: M (confidence: medium)

## Where it stopped
Built, round 1: all four acceptance tests pass, with the rest of `tests/test_redesign.py`. No overrun (about 86 net
lines). Choices made alone, each the reversible one:
- Links are `spec/causal.links` (flow↔stock material links and the causal links); "in a system" is at any depth
  (`spec.chain` of `correspond.system_of`); a part whose system is none or not declared is in none, so its links cross.
- A system added whose direct parts (renamed parts under their new names) are exactly those of a system taken away is
  read as that system renamed, so renaming a system alone adds no measure.
- Weight 3 in the ranking number (as findings and chains). Equal inside and crossing is neither worse nor improved.
- The review entry is `web/static/review.js` (a row in the scorecard table, not in Files to touch, but where the other
  measures are drawn); no browser file opens the review page, so it was not run in a browser, and `node --check` was
  refused here. SPEC §12e has the scorecard as prose, not a table: the prose was extended.
