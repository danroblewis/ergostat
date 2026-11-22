# cx-cyclomatic: branching in the code

depends-on: [cx-measure-frame]

Branch `cx-cyclomatic`, from main.

## The problem

The only shape measure today is functions over 60 lines. At 2468c59b the product has 4,192 functions with a median cyclomatic complexity of 5, 387 over 20, the worst 1% at 62 or more and one at 257. The tail is where the paths are, and nothing tracks it.

## The change

Family `dev/bin/cx_branching.py` and `dev/model/complexity-branching.yaml`.

## Definition of done

1. Per file (cached by blob), per function and method (nested ones counted apart): McCabe complexity = 1 + each `if`, `elif`, `for`, `while`, `except`, `with` is not counted, comprehension `for`, comprehension `if`, `match` case, conditional expression, `assert`, and each extra operand of `and`/`or`: the rules the common tools use, so the numbers compare. And its length in lines.
2. The row keeps, for **every** function, two histograms (`cyclomatic` value to count, `lines` value to count) and the sums; and the list `[qualname, cyclomatic, lines]` only for functions whose cyclomatic complexity is over 10 (for the report). Percentiles and medians are computed from the histograms over all functions, never from the list.
3. Series over the Python of the code scope:
   - stock `complexity-cyclomatic` (branches): the sum, headline pattern;
   - stock `complexity-functions-over-20` (functions), headline pattern;
   - auxiliary `complexity-cyclomatic-p99`, `driven-by: [+stock.complexity-cyclomatic]`;
   - cache only: `complexity-functions`, `complexity-cyclomatic-max`, `complexity-function-lines-median`, `complexity-function-lines-p90`.
4. Report `branching`: the 30 worst functions (path, name, cyclomatic, lines).
5. Python only: the descriptions say so, so that JS is not read as zero.

## Files to touch

`dev/bin/cx_branching.py` (new), `dev/model/complexity-branching.yaml` (new), `tests/test_factory_cx_branching.py` (new).

## Acceptance tests

- `test_counts_each_branch_kind`: a table of small functions with known complexity, one per construct, a comprehension `if` among them.
- `test_nested_functions_counted_apart`.
- `test_median_counts_small_functions`: 99 functions of complexity 1 and 3 lines and one of 25: the line median is 3 and p99 is 1 or 25 by the stated percentile rule, not a value of the tail alone.
- `test_splitting_a_function_keeps_the_sum_near`: the sum moves by the new function's 1 only.
- `ergostat check`: no new finding. Unit suite rc 0, ruff clean.

## Size budget

150 net lines outside `tests/` and `docs/`.

From the owner's request of 2026-11-22: measure ergostat's code complexity in many forms and slices, as stocks on main, backfilled from git history.

## Where it stopped

Built: points 1-5 and every acceptance test named above, in `tests/test_factory_cx_branching.py`, plus four more:
nearest-rank percentiles; a file that does not parse is no value and only the code scope's Python counts; the
`branching` report (order, the cap of 30, tests left out); the series' descriptions and parts say Python only. Nothing
within the definition is left. `complexity.py record`, named in the stocks' descriptions as in the frame's, belongs to
cx-backfill-run.

Choices made with nobody to ask (each easy to reverse):
- `complexity-cyclomatic-p99` is `driven-by: [+stock.complexity-cyclomatic, +flow.gaps-merged, -flow.removals-merged]`,
  more than point 3's `[+stock.complexity-cyclomatic]`. With the stock alone, `ergostat check` raised a new
  `system-splits@system.code-health`. The complexity subsystem grows from 3 parts to 12, which is at or over the
  architecture's `CLUSTER` of 4, and nothing links it to the rest of code-health. The two added causes are the ones
  `code-long-functions` already has. A flow measured by `changes:` cannot take a flow cause (`measured-not-caused`), so
  the auxiliary is the only place for them. With them, check finds nothing new.
- Percentiles and the median are by nearest rank: the smallest value with at least p% of all functions at or below it.
  For 99 functions of complexity 1 and one of 25, p99 is 1. With no function at all, the percentiles and the max get no
  value, never 0.
- What counts: the definition's list exactly. An `else` on a loop or a `try`, `finally`, `with` and `try` itself add
  nothing. Each `match` case counts, the wildcard included. Each `except` clause counts (`except*` too). A lambda's
  branches count in the function it is written in. A class body inside a function counts in that function, but its
  methods are counted separately.
- Names: `Class.method`, a nested function `outer.inner` (not Python's `outer.<locals>.inner`). Lines run from the `def`
  line to the function's last line, nested functions included and decorators left out.
- Histograms are kept as sorted `[value, count]` pairs, since the frame's row measures are numbers or lists. Per file the
  row also keeps `functions`, `cyclomatic` and `function_lines` (the sums).
- A `.py` file that does not parse is cached as `{"unparsed": why}`. Only in the code scope does it fail the family at
  that commit (no value, retried as the frame retries). Elsewhere (tests, docs) it is ignored. Files that are not Python
  measure `{}`. `ENV` is the Python minor version, since `ast` changes with it.
- The report lists at most 30 functions, from the over-10 lists only, so it is shorter when fewer than 30 are over 10.
  It is ordered by complexity, then lines, then path and name, all descending except path and name.
- `tests/test_factory_cx_frame.py` (outside the Files list, made necessary by this family): `test_the_commands` assumed
  `size` was the only family (`list` equality, `measure` output starting with `size`). It now reads the size family's
  lines. The frame's check test leaves out every `complexity*.yaml` in its "before" model, since this family's file
  needs the `complexity` system.

Size: 139 net lines in dev/ (cx_branching.py 105, complexity-branching.yaml 34), within 150.

Tests: `tests/test_factory_cx_branching.py` (26 passed, the `ergostat check` test among them) and
`tests/test_factory_cx_frame.py` (14 passed), each run alone. Ruff is clean. I broke the code and watched tests fail
(lesson-9) for three faults: comprehension `if`s not counted (the branch-kind test fails), a median taken over distinct
values (the median test fails with 30 for 3), and nested functions dropped (the nested test fails). The unit suite and
the browser files were not run here. This gap changes no page.
