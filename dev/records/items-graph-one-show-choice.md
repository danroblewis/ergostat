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
