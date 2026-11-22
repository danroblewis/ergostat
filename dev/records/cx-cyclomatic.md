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
