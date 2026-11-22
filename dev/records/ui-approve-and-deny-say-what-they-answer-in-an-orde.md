# ui-approve-and-deny-say-what-they-answer-in-an-orde: Approve and Deny say what they answer, in an order the keyboard can use

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q48 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list

**The problem:** No button anywhere is labelled Approve where only person asks wait; buttons are 'Deny' and 'Done' with no object; Deny comes before its reason box in tab order, so the keyboard path denies before a reason can be typed; Deny is borderless beside a bordered Approve.

**The change:** Buttons carry their object in the accessible name and, where it fits, visibly ('Approve the push', 'Deny the push'). Order in the row: sentence, reason field, Approve, Deny, with equal weight. Deny is disabled until a required reason is typed.

**User stories it serves:** E3, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Tabbing through a request reaches the reason field before the Deny button; each button's accessible name contains more than one word and is unique in the list; Approve and Deny have the same border style.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. 15 net lines outside tests (ergostat/web/static/diagram.js `inboxAnswer`, one field in ergostat/state.py).

- Each answer in the side list's *Needs attention* names its object, seen ("Approve the push", "Deny the push",
  "Done with reviewer's ask", "Approve the model change", ...) and heard (the same words plus the entry's id, so each
  accessible name is unique in the list even when two pushes wait). `attention()` now gives each entry an `object`
  (its action's or block's name) for this.
- Order in the row: sentence, (how many), reason field, Approve/Done, Deny. Deny lost its `ghost` class, so it is drawn
  like Approve.
- Decided without asking (the most reversible choice): in this list the reason counts as required for a denial, since
  its box already says "why (to deny)". Deny stays disabled until a reason is typed. Only the page enforces this:
  `ergostat inbox --deny` and the API still accept a denial with no note. The item page's own Approve/Deny
  (pages.js) is not touched, because the gap names only the /diagram side list.
- Found on the way: the list is refreshed by patching, and the answer's handlers read the inputs they were built with,
  not the ones on the page. The new order made that show, because the person's number box was patched onto the old
  reason box and Done sent no number. The handlers now read their row on the page. Deny's disabled state is built
  from the reason already typed there, so a refresh does not switch it off.
- Test: tests/test_inbox_page.py::test_approve_and_deny_say_what_they_answer_in_an_order_the_keyboard_can_use
  (the page's own browser file). It checks names (more than one word, unique), the Tab path (reason, Approve, Deny)
  with a reason typed on the way, the same border on both, Deny disabled while empty and still on after a refresh,
  and a keyboard denial recorded with its note. Seen to fail on each of four breaks: reason after the buttons,
  `ghost` back on Deny, one-word labels, and Deny never disabled.
- Run here: tests/test_inbox_page.py (2 passed, rc 0, Playwright, under the watchdog); tests/test_inbox.py and
  tests/test_gated_actions.py (40 passed); ruff clean. Not run here: the unit suite and the four browser files
  (the factory's and the merge queue's). Nothing to merge: `main` has not moved since the clone.
