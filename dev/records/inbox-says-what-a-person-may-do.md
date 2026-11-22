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
