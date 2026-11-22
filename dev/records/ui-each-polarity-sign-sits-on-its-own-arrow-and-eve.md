# ui-each-polarity-sign-sits-on-its-own-arrow-and-eve: Each polarity sign sits on its own arrow, and every top-level link has one

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q25 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram Dynamics, links between systems

**The problem:** Signs are stacked at the receiving edge where 7 to 15 links converge; the nearest sign is the wrong one (missing-ops → filed-features read backwards); deployed → shipped has no sign; driven-by links are solid though the README says dashed.

**The change:** Place each sign beside its own arrowhead, offset along that link, at 13 px or more, never within 10 px of another sign. Give every drawn link a sign or a '?'. Draw driven-by links dashed.

**User stories it serves:** B6, G3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796/ and :8793/ no two polarity glyphs' boxes overlap or lie within 10 px; each glyph's nearest link path is the link it belongs to (data attribute); every link has a sign glyph.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
