# guide-good-dashboard-panels: how to make sensible dashboards and panels

The owner, 2026-11-22: "We might also want instructions for how to make good sensible dashboard panels."

Change: `docs/DASHBOARDS.md`, linked from the agent guide and the `ergostat-author` skill, for agents and people:
- Start from the question a panel answers and the decision it supports. A panel with no decision is removed.
- Layout: the headline state first, then rates, then detail. Few panels, consistent time range, related panels aligned.
- Choosing the measure: rates for flows, counts for stocks, percentiles rather than averages for durations, arrivals beside completions, Little's law as a check; the RED and USE methods where they fit.
- Choosing the form: line, stacked area only for parts of a whole, bars for discrete periods, stat for a current value with a sparkline, table for lookups, and when not to use each.
- Units, scales, thresholds tied to real goals, legends beside the plot, cardinality limits, and no dual axes.
- Query cost: read the projection and metrics store, and what to do when a panel is slow.
- Recipes for common questions: is work flowing, where is it stuck, what does it cost, are we keeping up, what changed.
- Examples of a bad panel and its fix, using real `chartPanel` configs.

Definition of done: every example config in the document is loaded and validated by a test against the query API. It is added to `ergostat help`'s documents.
