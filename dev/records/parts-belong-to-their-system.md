# parts-belong-to-their-system: a part knows which system it belongs to, and is shown without the system's name where that system is known

depends-on: [remote-of-remotes-continued]

The owner, 2026-11-22: "systems should be namespaced, if a thing belongs to a system it should get prepended with the system name, we can remove the system name from the thing's name if we know the system's name."

Today composed names are made by joining strings (`f"{inst}-{bare}"` in `ergostat/library/expand.py:492,560`, `f"{remote}-{n}"` in `ergostat/remote/compose.py`). Nothing records the owner of a name, so a local `m-a-open` and remote `m`'s `a-open` can only be told apart by bookkeeping in each place, and a diagram inside system `m` repeats `m-` on every box.

## Definition of done
1. The compiled model records, for each part made by a library instance or a remote, the system it belongs to and its name within that system. A hand-written part in no such system records none.
2. Full names do not change: every existing model, event, record and reference keeps working, with no migration.
3. Where the system is known (a diagram or list inside that system's box, or its system page), the part is shown by its short name, with the full name on hover and in links. Where it is not, the full name is shown. Two parts shown side by side never read the same.
4. The short name is derived from the recorded owner, never by stripping text that happens to match.
5. SPEC says what a part's system and short name are.

## Files to touch
`ergostat/library/expand.py`, `ergostat/remote/compose.py`, the compiled model, the web payload and diagram labels, `docs/SPEC.md`, tests.

## Risks
- No new page or panel: only labels change.
- lesson-3: a part whose owner is unknown shows its full name.
- After any label change, run `tests/test_diagram_rendering.py`.

## Acceptance tests
- a library instance's part and a remote's part each record their system and short name
- a hand-written `m-a-open` beside remote `m`'s `a-open` keeps distinct owners
- inside a system's box the short name is shown, with the full name available; outside, the full name
- an existing example compiles to the same full names

## Size budget
200 net lines of code outside `tests/` and `docs/`.
