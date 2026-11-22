# ui-a-loop-is-called-r-or-b-only-when-every-link-has: A loop is called R or B only when every link has a sign

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q64 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram Dynamics markers; loop panel

**The problem:** R2 is 'Reinforcing' though 9 of its 12 links show no sign; one panel shows '(?)' for a link another shows as '+'. Rows mix 'stock:awaiting-deploy' and 'gap:all-live' with plain names. Markers carry an unexplained '+1'.

**The change:** Fill the signs that hold by definition (inflow → stock +, outflow → stock −, stock → its gap +, desired → gap −). If any link is still unsigned the marker reads '?' and the panel says which link. One sign per link across panels. Plain names, all links. '+1' becomes '2 alike' with a title naming the other loop.

**User stories it serves:** G3, G4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796 ?system=product every row of R2's 'Around the loop' table has + or −, or the marker's letter is '?'; no row text contains 'stock:' or 'gap:'; no marker text matches /\+\d$/.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
