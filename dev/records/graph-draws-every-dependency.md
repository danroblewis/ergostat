# The Items page's Graph draws every dependency of the unfinished work

## The problem

On a large record the Graph hides almost all of the work's dependencies. On the factory's record, with kind `gap` chosen, the answer from `/api/items-graph` is right: all 375 unfinished gaps and their dependencies are in it. The page then draws 2 of the 338 dependency lines into unfinished gaps, and 108 of the 375 unfinished gaps.

`rgModel` in `ergostat/web/static/relations.js` causes this in two ways:

1. **Items of a kind nobody asked for take the room.** The answer holds the items relations reach, and `rgModel` starts its scope from all of `d.items`. 190 of the 300 cards are `review` records, reached only because they name a gap. A review in state `merge` also reads as `active`, so these sort first.
2. **The cap cuts dependency chains apart.** Past `RG.NODES` (300) it keeps the first cards by status. Waiting items sort last, so a waiting gap and what it waits on are dropped, and a line is drawn only when both ends survive.

## What done means

- The scope starts from the items of the kinds asked (`asked` on the answer's kinds). Another kind's item is drawn only when an asked item waits on it through a precedence relation, or it is the parent of a drawn item. A record that only refers to an item, such as a review of a gap, is not drawn.
- With kind `gap` on a record of the factory's shape (about 375 unfinished gaps, about 340 dependency lines, about 340 review records), every unfinished gap and every dependency line into one is drawn. Raise `RG.NODES` as far as that needs, and keep a bound.
- Past the bound, the cut never separates a dependency: whole connected groups of items are kept or left out, those holding active or unblocked work first. The existing note says how many items and how many dependency lines are not drawn.
- A finished predecessor still follows the collapse setting (`via N done`).
- The Timeline's rows and the statuses' counts are unchanged, except where they read the same scope on purpose.

## Tests

Add tests beside `tests/test_relations.py` using a generated answer of that shape: no dependency line of an unfinished item is lost, a review record is not drawn, and a cut past the bound leaves no drawn item with a missing drawn-kind dependency unreported. The browser suite is not run on each merge at present, so the test must not depend on it alone.

Do not add a page, panel or control.
