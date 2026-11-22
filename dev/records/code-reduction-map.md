# code-reduction-map: a reviewed map of what ergostat's code can lose, each item with its evidence

depends-on: []

The owner, 2026-11-21: before ergostat is given to people, review and reduce the amount of code. This gap makes the map; later gaps do the cuts.

## Definition of done
1. `docs/proposals/code-reduction.md`: for `ergostat/` and `dev/bin/`, the candidates to delete, merge or simplify, each with: the files and lines, the evidence (no caller on main, a duplicate of named code, a superseded path named in SPEC or GAPS, a feature flag never set), the net lines it would remove, the risk, and the tests that cover it.
2. Ranked by lines removed per unit of risk. The total is stated, and so is what was looked at and not found removable.
3. The first ten items written as gap definitions in the house shape (definition of done, files, risks, acceptance tests, size budget).
4. No code changes. Every claim cites file:line on main.

## Files to touch
`docs/proposals/code-reduction.md` only.

## Risks
- lesson-8: "no caller" is checked with grep over the whole repository, tests and docs included, and says what was searched.

## Size budget
0 lines of code; the map under 700 lines.
