# The Items page's Graph shows milestones with their gaps

## What done means

- With kind `gap` chosen, each gap is drawn inside a frame for its milestone, titled with the milestone's name, state and how many of its gaps are finished. The Graph's existing grouped-frame drawing is used.
- A dependency between milestones is drawn as an arrow between their frames. Dependency lines between gaps stay drawn, including across frames.
- A completed milestone is folded to its frame by default, under the Graph's existing collapse-done setting. Gaps with no milestone are drawn in a plain frame, so they stand out.
- No new page, panel or control.

## Tests

From a generated answer: frames hold the right gaps, inter-milestone arrows are present, no dependency line is lost, and a completed milestone folds.

## Added 2026-11-22 (the owner: the Timeline is "all messed up", and the graph cannot show what is blocked)

The Timeline groups its rows by milestone in the same way: one summary bar per milestone (its span and how much is done), its gaps folded under it, open for active milestones. Rows are ordered by the schedule, what starts first at the top, not by the parent tree. A row's name is readable, not cut to a few characters. A milestone's frame in the Graph and its summary row in the Timeline say how many gaps are done, working, ready, and **blocked, and on what**. It never silently cuts to a fixed number of rows: past the limit it folds milestones.

## Where it stopped

Built, round 1, in `ergostat/web/static/relations.js` and `style.css` only (168 added, 28 removed: about 140 net
lines against the 600 budget); no server change: the `/api/items-graph` answer already holds each gap's milestone as a
group edge named `milestone` (pinned on a real record by `tests/test_milestone_frames.py`).

Decisions taken alone (nobody to ask), each the most reversible one:

- **Which groups are frames.** A group relation other than `parent`, to a kind not asked (a gap's `milestone` with
  kind `gap` chosen). A first version framed every group of a kind not asked, and turned the snapshot test's epics
  (`parent` of tickets, in another system) from hubs into frames: a change outside this gap, so `parent` stays a hub.
  Nothing names `milestone` in the code.
- **Folding a Timeline milestone by hand.** A triangle on its summary row (the row's own disclosure, like a system
  heading's), kept across refreshes. It is not a new panel or toolbar control, but it is a click target the
  definition did not name. The label still opens the item.
- **Timeline grouping only when the Graph has frames.** Without milestones (the roadmap example) the rows keep the
  parent tree; with them, frames and loose items are ordered by when they start, and members by when they start.
- **Folded frames.** A milestone with nothing drawn in it is one card: a completed one under Collapse done, and also
  one only waited on by a drawn milestone (so its arrow is not lost). A line from a collapsed gap in a folded
  milestone is drawn from that card.
- **"Readable" names.** The Timeline's label column is 340 px (was 250), and an id is cut only where it does not fit
  the column (about 48 characters at depth 0).

Tests: `tests/test_milestone_frames.py` (unit: a real record's answer has the shape the generated one assumes);
in `tests/test_items_page.py`, last in the file: `test_the_graph_frames_each_gap_in_its_milestone`,
`test_the_graph_draws_each_milestone_as_a_frame_holding_its_gaps[False/True]`,
`test_the_timeline_groups_its_rows_by_milestone_in_the_schedules_order`. Seen to fail with the milestone arrows
removed, with the folded-frame redirect removed, and with the Timeline's fold past the bound removed.

Not clean: `tests/test_items_page.py::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` fails
here (it waits 30 s for the other project's entry in the header's project switcher). Its test and code (header,
project switcher) are untouched by this branch, and it runs before the new tests. Running it with main's two static
files was refused in this session, so it is not shown to fail on main. With the new tests placed before the roadmap
Timeline tests, `test_the_graph_and_the_timeline_left_open_change_nothing[timeline]` failed in full-file runs (a
legend count button changed during its quiet window as the roadmap fixture aged) and passed alone. Placed last, it
passes. The cause inside that test (a count that moves with the record's age) is not fixed here.

Round 2 (the review's one finding, blocking): a Timeline summary row's span came from its drawn rows only, so under
the default Frontier + Collapse done a completed milestone had no bar, its tally was placed at x=-Infinity and its
arrow to the next milestone was dropped; an active one's bar covered only its unfinished gaps. Now the span is every
member the answer holds (the model returns `members`, already built for the tally), or the milestone's own times
when none has any; the order by start uses the same span; a tally with no span at all sits at the axis; a folded
milestone's collapsed gaps draw their lines from its row (as its drawn ones already did). The bar carries
`data-t0`/`data-t1`, read by the test. New test, last in the file:
`test_the_timeline_spans_each_milestone_over_all_its_gaps_under_frontier_and_collapse` (Frontier and Collapse on: the
completed milestone's bar over all 6 of its gaps, each bar the same span as with nothing collapsed, each tally at a
finite x, m0's arrow kept). Seen to fail with the old span (`x.kids`) put back, and with the summary rows' arrows
removed. About 145 net lines in the code against the 600 budget.

Not clean, round 2: in the full `tests/test_items_page.py` run, 37 passed and
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` failed, as in round 1; it fails alone too (a
30 s wait for the other project's entry in the header's project switcher), and nothing it covers is changed here.
Running it on an export of main (`git -C /work archive main | tar -x -C /tmp/mainsrc`, then the test there) was
refused in this session, so it is still not shown to fail on main.
