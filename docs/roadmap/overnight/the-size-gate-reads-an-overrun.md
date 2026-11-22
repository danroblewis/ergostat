# the-size-gate-reads-where-it-stopped: an overrun's written reason is seen where the rules put it

depends-on: []

## Definition of done

1. review.judge's size check (dev/bin/review.py, `net > budget and not re.search(over.*reason...)`) looks for the reason in the definition file at the branch's HEAD, not only in the text as committed first. That first-commit text is what gates() returns, so the budget and gate 1's unchanged check still use it. The house rules say a definition changes only by appending 'Where it stopped', which is where an overrun reason has to be written. Today the gate never reads it, so every overrun with a written reason loops on 'with no reason written' (gap/item-graph-queries: 4 reviews, 9.6h in fix; kb-about too).
2. The reason is taken only from what was appended after the first-commit text (the HEAD file must start with the committed definition), so a branch cannot edit its own budget or definition to pass.
3. A HEAD definition that cannot be read counts as no reason (lesson-3).
4. The finding's text says where the reason was looked for.

## Acceptance tests

- tests/test_review.py::test_an_overrun_reason_in_where_it_stopped_is_seen
- tests/test_review.py::test_an_overrun_with_no_reason_appended_still_blocks
- tests/test_review.py::test_a_reason_in_an_edited_definition_does_not_count

## Size budget

30 net lines

## Where it stopped

Built (round 2). In round 1 the gate searched appended prose with the loose `over.*reason` pattern, which failed
open. Now the gate reads an overrun's reason only in an allowlisted form: a line of its own that starts
`Overrun reason:` and has something after it, inside a `## Where it stopped` section the branch appended
(dev/bin/review.py, OVER_REASON and stopped()). Sections the factory's park() wrote ("Parked by the factory") and
text outside such a section do not count. The finding names the form, and dev/prompts/implementor.md tells
implementors to use it.

Choices made with nobody to ask (the most reversible ones):
- An allowlisted line form instead of round 1's suggestion (word boundaries near "reason"). Under that suggestion a
  quoted finding such as "the overrun ... with no reason written" would still have matched. Going back to it means
  changing one regex.
- The first-committed text is checked for the same form. Before, it was searched with the loose pattern, so a
  definition that only mentions an overrun and a reason ("every overrun with a written reason loops", as this one
  does) passed. A planner who wants to allow an overrun up front writes the same line.
- The gate no longer sees reasons written as free prose on other branches. It never saw them before round 1 either;
  such a branch needs to add one `Overrun reason:` line.

All changes are under dev/ and tests/, so 0 net lines count against the 30-line budget.

After the fast suites: the unit suite failed with one F, and its tail does not name the test. The cause found in
this branch: the size-gate tests' fixture loaded dev/bin/review.py and left dev/bin on sys.path and fac, agents,
brief, knowledge, parks and pools in sys.modules. fac fixes its MODEL to the cwd at import, so a later test in the
same xdist worker could pick up those stale modules (test_factory.py's `sys.modules.setdefault("fac", ...)`, for
one). The fixture now puts sys.path back and takes out only the dev/bin modules it added
(tests/test_review.py::test_the_size_gate_tests_leave_no_factory_module_behind; it fails with the cleanup
removed). The F was not reproduced here: tests/test_review.py with tests/test_factory.py, in either order, plus
tests/test_backlog.py and tests/test_outside_experiments.py, all pass alone. If the next unit run still fails, that
failure needs its name before anything more can be said.
