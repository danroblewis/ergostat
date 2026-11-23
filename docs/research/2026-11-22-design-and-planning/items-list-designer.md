# Owner items 1, 3, 4, 11, 12, 13, 14: the Items page (list, filters, Graph)

Designer's notes, 2026-11-22. Code read at ergostat main 2468c59b. Screenshots in `shots/plan-items-*`.
The live factory (:8798) did not answer any GET during this review (every request, `/api/status` included, timed out
at 20 to 90 s while several reviewers were probing it), so the live case is read from `scratchpad/gaps.json`, a
listing taken from it on 2026-11-21, and from `ergostat.yaml` (the factory's model).

## What a user sees today

**The list is a wall of finished work.** the-job (:8792) opens on a 23,000 px page: 12 systems and 19 kinds, every
kind's chart and its 25 newest rows, open or not. The `pr` table shows 25 rows of which 3 are open
(`plan-items-8792-top.png`); `mention` shows 25 of which 1 is open (`plan-items-8792-scrolled.png`). On the factory
the gap kind holds 92 parked, 31 merged and 7 closed beside 77 open; reviews 190, sessions 366, model changes 428,
almost all finished.

**A kind's heading cannot be found.** The system heading is an h2 with a fold triangle, but a kind's own heading
(`h3.kind-head`, "pr 25") is 14 px body text, placed *under* the kind's chart, with the count in grey. Scrolled into a
table (`plan-items-8792-scrolled.png`) nothing on screen says which kind or system the rows are; the column header
row is the only anchor.

**A filter click feels like a reload.** It is not one (no document load; `replaceRoute` + a refetch), but:
(1) choosing a state makes the page about that kind alone, every other kind's table disappears and the reader lands
mid-way in a different 300-row list (`plan-items-8792-afterfilter.png`); (2) the whole page is fetched again, and on
the-job the first draw took 11 s because each kind's chart asks `/api/items-flow` and each one takes ~2.5 s
(timed: `items-flow?kind=mention` 2.57 s, versus `items?kind=mention&state=triaged` 0.004 s); (3) the same request
was sent three times within 7 s (click, then the 4 s poll twice) with no cue that anything is under way. On the
live factory, where a request queues for minutes, a click shows nothing and then the page swaps wholesale.

**"Show all" is a cliff, not paging.** A kind with more than 25 shows `All N`, which switches the page to that kind
with up to 300 rows (`per_kind: 300`); beyond 300 nothing (on the factory: 366 sessions, 428 model changes). The
server already pages (`items.listing(n, offset)`, `in_states_page(states, n, offset)` over the item index); the page
never asks for page 2.

**Frontier does nothing you can see.** Read in `relations.js` `rgModel`: the scope is "every unfinished item and
every predecessor however far back". In **Graph**, *Collapse done* is on by default and removes every finished item
anyway, so toggling Frontier changes nothing (`plan-items-8794-graph.png` vs `-nofrontier.png`: same cards; the
differences are the demo moving on). In **Timeline**, where Collapse is off, the epics of the roadmap each wait on
the previous one ("after"), so "however far back" reaches every epic since e31: Frontier on still lists the whole
history (`plan-items-8794-timeline.png`); off, it adds only the finished tickets (`-timeline-nofrontier.png`). On the
factory, gaps `depends_on` chains do the same.

**"Collapse done": done is never named.** What counts as done is worked out on the server
(`precedence.Kinds._info`: `messages: done:` if declared, else "states after the first that no item has left",
minus queue, leased, dead and paused) and never sent to the page. `/api/items` gives each kind its states and counts,
no finished set. The reader cannot know that for gaps "done" is merged and closed, that parked is paused (not done),
that dead letters are their own status, or that for ticket-factory's `ticket` (no `done:` declared) the inferred set
is whatever states no item has left yet, which changes as items move. A one-state kind (`pool: [held]`) falls back to
its last state, so by that rule every pool is "done".

**The knowledge Graph holds gaps.** Kinds are put in systems by what counts them (`item_systems.py`): review, lesson
and knowledge are in `knowledge`. The Graph asks `items-graph?kinds=review,lesson,knowledge`, and
`precedence.build` follows *every* relation, both ways, six hops (`links_from`/`links_to`, HOPS=6, up to 400 pulled).
`review.gap` (a plain "about" relation, not precedence) pulls in each reviewed gap, and from there sessions and the
gaps' `depends_on` chains: the knowledge frame becomes a picture of the factory's gaps. SPEC §5a says this on
purpose ("the items their relations reach, of any kind"). It mixes two things: a dependency network (precedence, the
recognised diagram: a project network / Gantt) and an "about" graph (an invented diagram). Neither review, lesson nor
knowledge waits on anything, so the right Graph for `knowledge` is "these items do not wait on one another" (Q59).

## The design

One idea runs through all seven items: **each kind says which of its states are finished, and the page shows the
unfinished by default, everywhere** (List, Graph, Timeline), with one way to bring the finished back. Then each kind is
a closed section with a real heading, opened in place, paged, and filtered in place.

1. **Finished, said once.** The server sends each kind `finished` (states), `paused`, `dead` (has a dead letter
   state), `finished_from` (`declared` / `inferred` / `none`) and `lives_on` (no finished state: a one-state kind, or
   nothing declared and nothing inferable). One function, shared by the estimates, relations, the list and Q61's tag.
   A one-state kind lives on. The legend under each kind's chart marks finished states (outlined, Q56) and says
   "finished: merged, closed (declared)" or "(inferred: no item has left them yet)".
2. **The list: kinds closed, headings you can find.** Under each system heading, one bar per kind: the kind's title
   as a real heading (h3 at the size of today's h2 minus a step), its one-line description (Q61), "finishes" or
   "lives on" (Q61), and its state chips with counts in state order, unfinished first, finished greyed. Every kind is
   closed on load (the owner: item 13); the bar is the disclosure. Open kinds are in the address (`open=gap,review`),
   so a link or reload keeps them. Opening a kind fetches its first page, its chart and cycle chart; a closed kind
   asks nothing but its counts (one `/api/items` with no rows). While open, its bar is sticky under the nav, so a reader
   in the middle of its table sees which kind and which filter. Systems keep their headings; modelling and ergostat's
   own kinds come last, under a rule (R2).
3. **Filters in place, finished hidden by default.** A kind's chips are its filter. Default: every unfinished state
   on, finished and dead off; "+ finished 38" brings them back (`finished=1`), a click on a chip toggles that state
   (several may be on: `state=gap:ready,fix`). The existing address `/items?kind=gap&state=closed` still works: an
   explicit state is shown whatever it is. A click (a) changes the chip at once, (b) filters the rows already loaded
   at once, (c) refetches only that kind's page, aborting any request for it still under way, with "Loading…" in its
   bar, (d) never touches the other kinds and keeps the kind's bar where it was on screen. The poll refreshes open
   kinds only.
4. **Pages, not a cliff.** An open kind shows 25 rows and a pager in its bar and at its foot: "1–25 of 77 open ·
   ‹ › ". Page in the address (`page=gap:2`). Sort by a column sorts the whole filtered set on the server (up to 5,000,
   said when cut), not the 25 on screen. `All N` goes.
5. **Graph and Timeline: one choice instead of two checkboxes.** "Show: Open · Open and what they wait on ·
   Everything in the window". *Open*: unfinished only, a chain through finished items drawn as one dashed line "via N
   done" (today's collapse). *Open and what they wait on*: plus the finished items an unfinished one waits on directly
   (one hop, not "however far back"). *Everything*: all, nothing folded. Graph defaults to Open, Timeline to Open and
   what they wait on (opened at now, Q60). The legend says the count each choice hides ("968 done not drawn"). The
   word "finished" and the list of states is the same as in the list's legend.
6. **A system's Graph is its own dependency network.** Only precedence and parent relations pull items into a
   graph, and only of the kinds asked. A precedence edge to an item of another system's kind is drawn as a terminal at
   the frame's edge naming the item and its system ("waits on gap/x · factory"), as the diagram does for parts outside
   a system (SPEC: terminals at the edge). "About" relations (review → gap, session → gap) are not drawn as edges; a
   card lists them in its tooltip and the item page has them (Relations). A system whose kinds have no precedence says
   once "These items do not wait on one another, so there is no dependency graph" (Q59) and draws nothing.

### The owner's request and the review

- **Agree.** Q32 (search narrows kinds, says "nothing matches" by the box), Q36 (the address holds the selection,
  replaceState), Q11 ("Loading…" where it is loading), Q56 (finished states drawn apart), Q61 (each kind says what it
  is and whether it finishes): all point the same way, and the gaps below reuse or extend them rather than repeat them.
- **Combine.** Q61's "finishes / lives on" tag and the owner's "terminal states hidden" need the same definition;
  gap 1 makes it one function so Q61 does not invent a second. Q60 ("finished epics collapsed" on the Timeline) is the
  *Open and what they wait on* default of gap 5.
- **Conflict, resolved for the owner.** The review keeps "a folded system keeps its charts" (`test_items_page.py`
  pins it); the owner wants every list closed. Closed kinds keep their counts (the chips), not their charts: charts
  are 150 px each and cost a 2.5 s request each. The SPEC's "the items their relations reach, of any kind" (Graph)
  changes to precedence and parents only, and only the system's own kinds as cards.
- **Rules.** No new page or panel: the kind bar replaces the chart-then-h3-then-table stack; the Graph and Timeline
  keep their recognised forms (project network, Gantt) and lose the invented "about" graph. Read-only: filters only.
- **Item 15 (the kind's page, another cluster).** `item-kind-and-show-engineer.md` proposes `/items?kind=K` as the
  kind's page, depending on this cluster's gaps. The kind bar of gap 2 is that page's header; gaps 3 and 4 are its
  filter and pager. Nothing here closes off a later `/kind/K`.

## Gaps

| # | name | size | items | depends on |
|---|---|---|---|---|
| 1 | items-kinds-say-which-states-finish | quick | 4, 1 | – |
| 2 | items-list-kinds-closed-under-real-headings | incremental | 11, 13 | 1 |
| 3 | items-list-hides-finished-and-filters-in-place | incremental | 1 | 1, 2 |
| 4 | items-list-pages-through-a-kind | incremental | 14 | 2, 3 |
| 5 | items-graph-one-show-choice-for-finished | quick | 3, 4 | 1 |
| 6 | items-graph-draws-the-systems-own-dependencies | incremental | 12 | – |

Parallelism: 1 and 6 start now; 2 and 5 after 1 (in parallel); 3 after 2; 4 after 3. None needs a proposal first:
each is one surface with its design settled here. Full definitions are in the structured result.

## Questions for the owner (one sentence each)

- Are merged gaps also "no longer interesting" (hidden by default with closed and dead), or should merged stay
  visible for a day?
- Should a kind you open stay open next visit (remembered in the browser), or always start closed?
