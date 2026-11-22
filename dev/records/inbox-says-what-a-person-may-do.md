# inbox-says-what-a-person-may-do: The requests group opens with one sentence saying what a person may do here

depends-on: []

Problem (R3 piece 9, story A4): decision 7 makes approving or denying the one thing people do, and nothing on the page says so. A newcomer cannot tell whether clicking a part changes the system (shots/story-4-home.png, ixdb-tf-approve-item.png).
Change: at the head of the requests group in Needs attention (ergostat/web/static/diagram.js:1347, the group filed Q42 heads 'Waiting for you'), and at the head of the Actions page, one muted sentence: 'You can look at everything. Approving or denying these is the only thing that changes the system.' With no request waiting the group reads 'Nothing waits for you. Looking never changes the system.' The sentence is announced once with the group (aria-describedby), not on every poll.
Definition of done:
1. On a fixture with requests waiting the sentence is the first text of the group; with none, the empty form shows.
2. The same sentence is on the Actions page.
3. A screen reader reads it once when focus enters the group (the group has aria-describedby pointing at it).
4. At 390 px it wraps without overflow.
Files: ergostat/web/static/diagram.js, pages.js (Actions), style.css, tests/test_diagram_rendering.py.
Acceptance tests: a browser test for 1-3.
Budget: 20 net lines.

Milestone: r3-needs-attention-is-the-inbox. Owner items: R3 piece 9 (pieces 1-8 are filed Q42-Q51, Q77; piece 10 is in demos-upkeep-holds-and-actions-wait). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. Two choices made with no one to ask, each the more reversible one:
- There is no 'Waiting for you' requests group on main yet (Q42 has not landed). So the sentence opens the whole
  *Needs attention* list (`.att`, now `role="group"` with `aria-describedby="may-do"`). The long form shows when any
  entry there has an answer (a request), and the empty form when none does. Once Q42 lands, the same `p#may-do` moves
  to the head of its group.
- There is no Actions page: gated actions are the Items page with `kind=ergostat.action`, and the house rules forbid
  new pages. So the sentence heads the Items page when that kind is chosen, and nowhere else on it.
Acceptance test: `tests/test_diagram_rendering.py::test_the_requests_group_opens_by_saying_what_a_person_may_do`
(waiting and none). It covers 1-4: first text of the group, the empty form, the Items-page sentence, aria-describedby
with no live region, a redraw that neither replaces nor changes the node, and no overflow at 390 px. "A screen reader
reads it once" is checked through those DOM facts, not with a real screen reader. Five breaks were each seen to fail
it: no aria-describedby, always the empty form, an attribute changed on each render, `white-space: nowrap` (fails
only the long form, since the short one fits at 390 px), and the Items-page sentence never shown.
Net lines outside tests and docs: 8, within the 20 budget.
