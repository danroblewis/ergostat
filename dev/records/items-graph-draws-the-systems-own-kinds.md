# items-graph-draws-the-systems-own-kinds: A system's Graph draws only its own kinds' dependency network; another system's items are stubs at its edge

depends-on: []

Problem: in the factory, review is counted in the knowledge system (instance dev/model/knowledge.yaml:44,252; spec/item_systems.py rule 2) and declares relations {gap: gap}, a plain 'about' relation. The page asks items-graph for each system's kinds with relations (ergostat/web/static/pages.js:670-678) and precedence.build follows every relation both ways for HOPS=6 up to 400 items of any kind (ergostat/precedence.py:40-41, 274-299), so the knowledge Graph fills with gaps, their sessions and depends_on chains drawn as full cards on 'gap' edges. The owner cannot tell why gaps are there. SPEC §5a says 'the items their relations reach, of any kind' on purpose (docs/SPEC.md:1547), so the SPEC changes first (open owner question; the gap proceeds on this default).
Change: (1) items-graph takes system=NAME (relations_api.kinds_asked accepts it); build() then pulls further items only along precedence and parent (group) relations and only of the system's own kinds. (2) a precedence target or parent of another system's kind is not a card: the answer marks it outside: true with its system and rgModel draws a small stub at the frame's edge ('waits on gap/x, ready · building'), linked to /item/ID; its status still counts (the existing cut/beyond logic), so the waiting item stays 'waiting'. (3) 'about' relations are not edges; they are listed in the card's hover text and stay under Relations on the item page. (4) a system whose kinds declare no precedence or parent relation draws no canvas and says once 'These items do not wait on one another, so there is no dependency graph' (filed Q59's sentence) and where the related items are ('reviews are about gaps: see building'). (5) items-graph without system= keeps today's behaviour for the CLI. MOST_PULLED and HOPS stay for chains inside a system.
Definition of done:
1. SPEC §5a's Graph paragraph states the new rule.
2. On a fixture shaped like the factory (review in knowledge with gap: gap; gap elsewhere with depends_on) the knowledge answer has no gap as a full item and its section shows the sentence and the link.
3. A ticket in system A blocked by an item in system B shows one stub naming B, and the ticket is 'waiting' while B's item is unfinished.
4. The gap's own system's graph and critical path are unchanged; on the roadmap fixture the delivery Graph has the same card count.
Files: ergostat/precedence.py (build), ergostat/web/relations_api.py, ergostat/web/static/pages.js (relAsked by system, the sentence), relations.js (stubs, hover text), style.css, docs/SPEC.md, tests/test_relations.py, tests/test_precedence_cap.py, tests/test_item_graph_queries.py.
Acceptance tests: unit tests of build() on the two fixtures; build(kinds=[gap]) still returns the depends_on chain; a browser check on the roadmap fixture.
Budget: 160 net lines.

Milestone: items-page-readable. Owner items: 12. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1; nothing left of the definition. 85 net lines of code (budget 160). Choices made alone, each the more
reversible one:
- The stubs are a list of their own in the answer (`outside`, each `outside: true` with its `system`), with edges of
  kind `outside`, not entries in `items`: the Timeline, the legend's counts, the estimates' merge and `order_ready`
  read `items` and are untouched. Capped at MOST_PULLED (`capped.outside`, said by the legend); past it their status
  still counts.
- The page asks `kinds=` (its kinds with relations, as before) and `system=` together; `system=` alone still means the
  system's kinds. Only the Graph gives way to the sentence; the Timeline of such a system is still drawn.
- `ergostat/web/snapshot.py` (outside the Files list) asks the same `system=` keys as the page, or a snapshot would
  lose its Graph; tests/test_graph_cli_web.py's three snapshot tests follow it. The SPEC's open question (the owner
  may want "of any kind" back) is not answered here.
- "reviews are about gaps" is the kind's name and an "s"; a kind whose plural is not that reads oddly.
Not done: no screenshot was taken (a scratch script outside the repository was refused in this session).

Round 2: main (bf6dbebf) merged in. Its graph-draws-every-dependency had changed the same Graph paragraph of SPEC §5a
and `RG` in relations.js. Both are kept: main's 600 cards, its connected-group cut and its sentence on the kinds asked,
plus the branch's stubs (`STUB_H`, "400 stubs", "another system's: a stub"). The "other relations dashed and named"
clause now applies only without `system=`. tests/test_items_page.py fails 6 of 33, the same 6 on two runs, all on the
diagram's side panel (`#detail .item-set`, `.counts-line`, `.leases-line`, a snapshot's sets, the header counts),
which the branch does not touch. They were not run on main: a scratch worktree of main under /tmp was refused.

Round 3: main (b9341591) merged in; conflicts in SPEC §5a, precedence.build, relations_api, snapshot, pages.js,
relations.js and two test files resolved keeping both sides: main's levelled schedule (`build(lanes=)`, the cache key
on the lanes), its milestone frames, its sentence for a system without relations and its Timeline of such a system's
kinds (`held`, asked with `system=` too, in the page and in a snapshot), its `finished=` choice; and the branch's
`own`, stubs, `waits: false` sentence and hover text. tests/test_graph_cli_web.py's new snapshot test of a system
without relations now looks for the key with `system=desk`, as the page asks. The review's blocking finding is fixed:
the Graph's cap note counts only cards (`rgCapNote`, stubs not counted as items drawn), and
`test_a_capped_graph_with_stubs_counts_only_its_items_as_drawn` (1200 open gaps, 50 stubs) fails on the old count
("650 of 1219 items drawn: 569 items") and passes on the new one. docs/GAPS.md is put back as main has it (the round-2
merge had changed a line of another gap's entry there; `git checkout b9341591cb70 -- docs/GAPS.md` was refused, so the
line was restored by hand); the entry is below. tests/test_items_page.py: 90 of 93 pass;
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` and
`test_every_surface_prints_the_servers_one_count_of_goals_off` expect a "Loops" heading where main's page now says
"Goals" (main's goals-page rename; the branch touches neither), and
`test_a_lease_taken_or_ended_comes_and_goes_in_the_valves_panel` (the diagram's side panel) failed in the file's run and
passed alone; none was run on main here.

Round 4: the queue's finding fixed. `tests/test_queue_batch_item.py::test_the_timeline_draws_one_bar_per_run_and_the_gaps_link_to_their_batch`
(main's, from queue-batch-item) looked up the snapshot key `items-graph?kinds=batch`; since this branch the snapshot asks
by system, as the page does, so it failed with KeyError. It now finds the one `items-graph?kinds=batch&system=...` key
and checks the batch is in it (as tests/test_graph_cli_web.py did in round 3). Without `system=` in snapshot.py it fails
again (no key found), and it failed on the old key before the change. The file's page test,
`test_the_items_page_draws_the_batch_and_one_timeline_bar_per_run`, fails under Playwright at its first step, the kind's
list: the batch is finished (partial) and the list hides the finished by default (`fin()` is "hide" outside the
Timeline, pages.js:681; "1 finished (partial) not shown"). The branch touches neither the list nor its `items` answer,
so it is left alone (lesson 13). In queue runs it is skipped (no Playwright in that unit file). Run here with the list
step taken out, its Timeline part (which reads this branch's `system=` answer) passed; the step was then put back as
main has it. Not run on main here.

Round 5: main (d0f95413) merged in. Main's the-kind-page had moved the Graph and the Timeline from `/items` to a kind's
page (`/items/K`, asking `kinds=K`); pages.js merged on its own, so a kind's page asks `kinds=K&system=<its system>`.
SPEC §5a's paragraph is resolved as main's kind-page wording carrying the branch's rule. The "see building" link
scrolled to a system's section, which a kind's page has none of: it is now a link to the named kind's page, its Graph
(`kindHref(a.to, "view=graph")`), the more reversible choice. The branch's three browser tests that opened
`/items?view=graph` (the factory-shaped one, the roadmap's card count, now against `kinds=ticket`, and the capped
graph's stubs) open a kind's page instead; the factory-shaped test now clicks the link and finds the gaps' Graph. In
main's snapshot test the ticket's page draws planning's epic/e1 as a stub, not a card, so its Timeline has no epic row
(3 segments, not main's 4): the test says so. tests/test_items_page.py: 104 of 108 pass in the file's run; the capped
graph's test then passed alone, with the valves-panel test (also failed in round 3's file run, passed alone again);
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` and
`test_every_surface_prints_the_servers_one_count_of_goals_off` fail on the header and project switcher ("Loops" vs
"Goals"), untouched here. tests/test_queue_batch_item.py's page test fails at the list step as in round 4. Unit files
test_relations, test_precedence_cap, test_item_graph_queries, test_graph_cli_web, test_queue_batch_item pass; ruff
clean. A walk of the roadmap's ticket Graph loaded with no console error, but no screenshot was kept: `--shots /shots`
gave "Permission denied", and `mkdir -p /tmp/shots` was refused.

Round 6: the review's blocking finding fixed. With `own=`, build() now also reads, for the projection only, what the
system's items wait on in another system and what that waits on in turn (precedence and parent links out, the
unfinished followed on, up to HOPS and within MOST_PULLED: `shadow`). Those items are in the statuses, cycles, cpm and
the levelling as on main, but never in `items` or `edges`, nor in `critical` or the answer's kinds; the stubs are the
drawn items' direct targets among them (or past the cap, in `beyond`, as before). So a ticket blocked by an active
gap/c is projected after gap/c's expected end, and a child of epic e2 (after e1, both in another system) after e1's
children. `test_an_item_waiting_on_another_systems_item_is_projected_after_it` (es >= gap/c's ef; es, ef, slack,
critical, `end` and the critical path equal to the build without `system=`, restricted to tickets) and
`test_a_child_of_another_systems_parent_still_waits_for_what_that_parent_waits_on` both fail with the read turned off
and pass with it. SPEC §5a says the stub's schedule counts. The snapshot test's "3 segments" stays true: it counts the
Timeline's rows' segments, and epic/e1 is still a stub, not a row. Ran: tests/test_relations.py,
test_precedence_cap.py, test_item_graph_queries.py, test_graph_cli_web.py, test_queue_batch_item.py (its page test
skipped there, no Playwright in a unit run, as round 4 says), and under Playwright test_items_page.py's
`test_a_systems_graph_draws_its_own_network_and_says_when_there_is_none`,
`test_the_roadmaps_delivery_graph_is_asked_by_its_system_and_draws_every_card`,
`test_a_capped_graph_with_stubs_counts_only_its_items_as_drawn`, `test_a_snapshot_draws_the_graph_and_timeline` and
`test_the_timeline_draws_what_happened_and_what_is_projected`: all pass; ruff clean. 112 net lines of code against
main (budget 160). No screenshot (as in round 5).

## Entry

section: Interface

- **A system's Graph draws its own kinds** (done, on `items-graph-draws-the-systems-own-kinds`; SPEC §5a): a kind's
  page asks `items-graph` with its `system=`, so its Graph follows only precedence and parent relations to its
  system's own kinds; another system's item it waits on is a stub at the edge, its status still counted; an *about*
  relation is in the card's hover text, and a kind with no dependency says so and where its items point ("reviews are
  about gaps: see building", a link to the gaps' page). Left: the owner's question whether "of any kind" should come
  back.
