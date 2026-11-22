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

## Where it stopped

Built (12 net lines of code). Each Dynamics loop now carries `around`: every link around it, worked out over the
whole model before any system is closed (`_around` in ergostat/dynamics.py). Each link is signed as its connector
is drawn, with flows and gaps signed by definition, and both ends go by plain names. The panel, the marker and the
side list's row all read from it.

One file outside "Files to touch": ergostat/dynamics.py (22 lines). The page alone cannot sign a link whose ends
are inside a closed system, because the folded graph no longer holds them. The server's connector signs are the
ones the drawn lines use, so one sign per link holds across panels.

Choices I made alone (each is easy to undo):
- The side list's loop rows follow the same rule as the marker (a '?' tag and "Polarity not known"), so no panel
  calls a loop R or B when its marker reads '?'.
- A loop whose links are all signed, but whose count of minus signs disagrees with the model's polarity, also reads
  '?', and the panel says they disagree. Not seen in software-factory.
- Stock → gap and desired → gap follow the convention the connectors already use: + and − for a ceiling's excess
  (as this definition says), − and + for a floor's gap.

Tests: test_a_loop_is_called_r_or_b_only_when_every_link_has_a_sign (tests/test_diagram_rendering.py) was seen to
fail on four breaks: '+N' put back; ids in place of names; flow signs dropped while the marker kept 'R2'; the gap
sign flipped in the panel (caught in open=*). Also test_each_loop_gives_every_link_around_it_a_sign_and_a_plain_name
(tests/test_dynamics_view.py), and SD_CHECK's marker-letter check now reads the same rule. Not run here: the unit
suite and the four browser files as a whole.
