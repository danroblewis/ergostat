# items-graph-one-show-choice: Graph and Timeline read the page's one finished choice, with a middle level 'and what they wait on', replacing Frontier and Collapse done

depends-on: [items-list-hides-finished-by-default]

Problem: in Graph, Collapse done defaults on (pages.js:566) and removes every finished item with no unfinished child (relations.js:52); Frontier only decides whether those same items are in scope (relations.js:43), so toggling it changes nothing (reproduced on :8794: shots/plan-items-rm-graph-frontier1.png and -frontier0.png identical). With both off about 1,000 finished cards are drawn unreadably small (plan-items-rm-graph-f0c0.png). In Timeline, Frontier keeps every predecessor 'however far back', so on roadmap the whole history is still listed (plan-items-8794-timeline.png vs -timeline-nofrontier.png). Neither names what 'done' is.
Change: remove the two checkboxes (pages.js:688-689). Graph and Timeline read the page's one finished parameter through itemsFinished() (items-list-hides-finished-by-default owns it; that is the dependency), and the page's one control becomes a three-way segmented control 'Finished items: Hidden / Those waited on / Shown' writing finished=hide|waits|show. hide: unfinished and paused items only; a chain through finished items is one dashed line 'via N finished'. waits: plus finished items an unfinished one waits on directly (one hop). show: everything in the window. The list view treats waits as hide. Default hide everywhere; Timeline opens on waits unless the address says otherwise (a default, not a second control). Old frontier= and collapse= are read once and mapped. The legend says what is not drawn and why: '968 finished not drawn: gap merged, closed', from the answer's kinds[].finished (precedence.py:412). rgModel takes o.finished. The RG.NODES cap note stays for show.
Definition of done:
1. The two checkboxes are gone from both views; no 'Frontier', 'Collapse done' or 'Show: Open' text remains; the page has one finished control in all three views.
2. On the roadmap fixture the three options draw strictly increasing numbers of cards or rows.
3. waits never adds an item more than one precedence link from an unfinished one.
4. The legend names each kind's finished states and the count not drawn.
5. /items?view=graph&frontier=0&collapse=0 opens with Shown pressed; switching list -> Graph keeps the choice.
6. SPEC §5a table rows for Graph and Timeline updated.
Files: ergostat/web/static/relations.js (rgModel), pages.js (viewBar, go), style.css, docs/SPEC.md, tests/test_relations.py, tests/test_items_page.py.
Acceptance tests: unit (rgModel on a chain a->b->c->d, a-c finished, d unfinished): hide draws {d}, waits {c,d}, show {a,b,c,d}; browser on the roadmap fixture: .rg-card counts strictly increasing; old address maps.
Budget: 120 net lines.

Milestone: items-page-readable. Owner items: 3, 4. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. About 20 net lines outside tests and docs (pages.js +26/-21, relations.js +23/-11, style.css +1).

- **rgModel** takes `o.finished` (hide|waits|show; anything else is hide). hide: the old Frontier + Collapse done
  (the unfinished and what they wait on are in scope; every finished one is collapsed, a chain through them one
  line "via N finished"). waits: the same, but a finished item an unfinished one in scope waits on directly is not
  collapsed. show: no frontier, nothing collapsed. It returns `unseen` (the finished not drawn, per kind), and the
  legend says "N finished not drawn: KIND STATES; ...". Under show nothing is counted there; the RG.NODES note stays.
- **The page**: the "Show finished" checkbox and the Frontier and Collapse done checkboxes are gone. One segmented
  control, "Finished items: Hidden / Those waited on / Shown" (`.fin-seg`), is in the filters bar in all three
  views. Timeline's default is waits; the list reads waits as hide.
- **Choices taken alone (the reversible ones):**
  - A finished parent that has unfinished children stays a hub under hide and waits, as it did under Collapse done.
  - `finished=` is written only once a reader has chosen, or an old address has mapped. `hide` is written only on
    the Timeline (so a reload keeps it).
  - Old addresses: `frontier=0&collapse=0` maps to show, `collapse=0` alone or with `frontier=1` to waits, any other
    to hide. Neither is written again.
- **Not as the definition words it:**
  - The roadmap test counts `.rg-graph .rg-node` and `.rg-timeline .rg-row`: the page has no `.rg-card` class, and
    a card is `.rg-node`.
  - The "unit" chain test is `tests/test_items_page.py::test_rg_model_draws_each_finished_choice_on_a_chain`, run
    in the browser through `pg.evaluate`. No JS runtime (node) is on this machine, and a browser test kept in a
    unit file would be skipped by every gate (lesson 9). So `tests/test_relations.py` is unchanged.
- **Acceptance tests**: `test_rg_model_draws_each_finished_choice_on_a_chain` (items 2-4, plus the one-hop check on
  the factory and milestone answers), `test_the_graph_draws_the_unfinished_with_the_finished_collapsed` (items 1,
  2 and 4 on roadmap: Hidden < Those waited on < Shown cards; the legend line),
  `test_the_timeline_draws_what_happened_and_what_is_projected` (item 2 for rows), and
  `test_an_old_graph_address_opens_with_shown_and_the_choice_survives_a_view_switch` (item 5). SPEC §5a: the Graph
  and Timeline rows and *Finished items* are updated (item 6).
- **Seen to fail (lesson 9):**
  - With waits widened to every predecessor of anything in scope, the chain test fails at its waits assertion.
  - With the old-address mapping switched off, the old-address test fails.
  - Both were restored, and the tests pass on the committed code.
- **Failures not caused by this branch (left alone, lesson 13):**
  - `tests/test_queue_batch_item.py::test_the_items_page_draws_the_batch_and_one_timeline_bar_per_run` fails at
    line 306, before anything this branch changed. The batch ended `partial`, a finished state, so the list leaves
    it out by default (items-list-hides-finished-by-default). A scratch run showed "1 finished (partial) not shown",
    with no page errors. The Timeline step after it, with the new Shown button, drew the six expected bars.
  - `tests/test_items_page.py::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` times out
    waiting for the header's project switcher (`/api/projects`, server.py `_LISTED`; util.js), which this branch
    does not touch. It fails alone too. Not run on main here: extracting main into /tmp was refused.

Round 2: main (059ff718) merged. Its one conflict, docs/SPEC.md §5a, was resolved like this. The Graph row is the
branch's (main's text with Frontier and Collapse done replaced). The Timeline row is main's newer text (the
simulated schedule's order, Not scheduled, the capacity note), with only its last sentence swapped for the branch's
Finished items default. No code conflicted. After the merge, ruff is clean and the four acceptance tests pass.
The full `tests/test_items_page.py` run (twice): 78 passed, 3 failed, none caused by this branch (lesson 13):
  - `test_the_graph_and_the_timeline_left_open_change_nothing[graph]` passes alone and fails in the full file. A
    scratch observer (not committed) showed that the one change is the window menu button going from
    "Last 1h (50m recorded)" to "(51m recorded)": a wall-clock minute crossing during the test's watch (lesson 10),
    in code this branch does not touch.
  - `test_every_surface_prints_the_servers_one_count_of_goals_off` expects an h1 "Loops · ..." where main's
    goals-page-replaces-loops-page now draws "Goals · ...". The test is the same as on main.
  - `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`: as in round 1.
  - `tests/test_queue_batch_item.py::test_the_items_page_draws_the_batch_and_one_timeline_bar_per_run` still fails
    at line 306, as in round 1; the other 15 tests in that file pass.
