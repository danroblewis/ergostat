# header-status-out-of-the-nav: the header's status text stops crowding the navigation

The owner, 2026-11-23, about the text at the top of every page ("20 goals off · model upkeep 2 · 3 wait for you · Stalled: nothing takes intervention items from open: no block's t..."): "it makes the actual nav bar unusable, it is duplicated in other places, the majority of the text could be tooltips, the longest 'Stalled' part means nothing to me because its so long it gets cut off and theres no other way to see it, not that i would want to see it."

Change (ergostat/web/static: the header status in diagram.js and main.js, its styles):
1. The navigation (page links and the time window) always has room and is never pushed off or cut by status text, at desktop and phone widths.
2. The status shrinks to at most two short counts in the header, for example "20 off" and "3 for you", each a link to where it is detailed, with the full wording in its tooltip (title).
3. "model upkeep" moves into the tooltip of the goals count.
4. The "Stalled: ..." sentence is removed from the header. It is already said on the pages that detail it.
Small: about 60 lines, no new page or panel.

Definition of done.
1. A browser test at 1280 and 390 px wide: every navigation link is visible and clickable, and no header text is cut off.
2. The counts' tooltips hold the full wording, and each count links where it did before.
3. Do not measure or change the live instance in the session.

## Where it stopped

Built, round 1. The header status was written in util.js (refreshHeader) and index.html, not diagram.js or main.js
(diagram.js's caption is the Diagram page's own h1 and is left as it was). Net code outside tests and docs: about +5.

- The goals count (`#running`) says `N off`, a link to `/goals`; its title is the full wording (`N goals off`, with
  `, not running` when no engine runs), then `model upkeep J`, then each system goal off by name. Before this branch
  the count was a span that linked nowhere, so "links where it did before" has no old target for it; `/goals` is where
  the count is detailed (the definition's item 2). With no goal off and no upkeep it still says `Running` or
  `Not running`.
- `N for you` (`#waits`) keeps its link to `/diagram#waiting` and its polite live region; `N wait for you` is its title.
- `#upkeep` and `#heldup` are removed from the header. `held_up` stays in `/api/status` and `/api/held-up`; the root
  is said on an item's page ("Why isn't this done?") and by `ergostat held-up`.
- Choices made without the owner (each a one-line revert): the edited-model banner, an 80-character sentence, is also
  shortened to `Model errors` (a link to `/check`; the sentence and every error in its title), and "public, read only,
  no login" to `· public` (the full sentence in the title). SPEC §5a, the upkeep paragraph and the reload paragraph say
  the new header.
- CSS: the tabs no longer shrink and scroll sideways under the status (`flex: 1 0 auto`, wrapping); with too little
  room they take a row of their own. The phone rule putting `N for you` first (design review Q43) is kept.
- Acceptance: `tests/test_items_page.py::test_the_header_status_leaves_the_navigation_its_room[1280|390]`. Seen to fail
  on main's header at both widths: at 1280 the nav is squeezed into a scrolled box, at 390 the Stalled text is cut;
  with the Stalled assertion removed, it still fails on the nav and the cut text.
- Not done: no `## Entry` is added to this record (the definition may change only by this section).
- Failing on main as well, not from this branch (seen to fail identically with main's code and tests):
  `test_items_page.py::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` (the switcher never
  lists the other project) and `test_items_page.py::test_every_surface_prints_the_servers_one_count_of_goals_off`
  (the Goals page heading is "Goals · ...", the test wants "Loops · ..."). Both now pass the header assertions this
  branch changed before reaching the failing line.
- Round 2 (the queue's finding): `tests/test_style_tokens.py::test_below_760_px_the_tabs_wrap_and_never_scroll_sideways`
  failed because round 1 dropped `flex-wrap: wrap; overflow-x: visible` from the 759 px rule as redundant with the
  base rule. They are restored there (one line of style.css); the test was seen to fail without them and passes with
  them, and the acceptance test still passes at 1280 and 390.
