# milestone-progress-per-group: each milestone shows how far along it is

depends-on: [milestone-every-gap-has-one]

Owner, 2026-11-23: "if we have milestones and groups of gap tasks, then I probably also want to see progress per group, right?"

Change.
- Each milestone reads as: done, in progress, waiting, stopped, of its total, with its state (active, waiting on another milestone, completed) and what it is waiting on. Closed gaps count as done only when they were finished; a gap closed as a duplicate or abandoned leaves the total.
- It is shown through what exists: a compact row per milestone with a progress bar in the Items overview for the gap kind and on its kind page, active milestones first, and each row opening that milestone's gaps in the list, graph and Timeline. No new page.
- The numbers come from the item index, never by replaying events, and are available to dashboard panels: gaps by milestone as a category, grouped by state group, and each milestone's completion over time.
- Gaps with no milestone appear as their own row, so the unassigned share stays visible.

Definition of done.
1. A hand-worked record gives the right counts per milestone, including split, closed-as-duplicate and parked gaps.
2. A milestone's row links to exactly its gaps.
3. Twenty-five milestones fit without pushing the item types below the fold (collapsed past the active ones).
4. A dashboard panel can chart gaps by milestone, stacked by state group, with no custom code.

Files: dev/bin/milestones.py, ergostat's items pages and query fields, tests.
