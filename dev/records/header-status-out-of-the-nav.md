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
