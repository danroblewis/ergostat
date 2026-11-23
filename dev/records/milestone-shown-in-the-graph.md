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
