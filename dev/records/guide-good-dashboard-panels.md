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

## Where it stopped

Built, round 1. `docs/DASHBOARDS.md` covers every bullet; it is `ergostat help dashboards` (helpdocs.DOCS, and the
wheel's force-include), linked from docs/AGENT-GUIDE.md section 5 *Docs*, the ergostat-author skill's reading list and
the README. Acceptance: `tests/test_dashboards_doc.py` (34 tests) loads all 26 panel configs (every `json` block in the
document must carry a `<!-- panel: ... -->` mark), checks keys, form, options and display against what
`static/panels.js` declares, asks each panel's queries of `/api/query` over a seeded record of the document's own
example model and requires an answer with a value, and checks seven stated rules (good panels keep all, each bad panel
breaks exactly the one it is marked with). Seen to fail: the averaged p90 on a recommended panel, and the guide
removed from helpdocs; six in-test breaks of a panel are refused.

Choices made alone (the most reversible): "the projection" in the query-cost bullet is read as the item index (the
fold of the record, a projection in the event log's sense), since the query API does not chart the model's forward
projection, and the document says so. The checks run in Python against the query API, not in a browser: the option
registry is read from panels.js's source for the four core forms (line, bar, stat, table), the only forms the
examples use. Little's law's W is the mean time in state, the one average of a duration the document allows (on a
stat; the rule bans averages on lines and bars). Not run here: the unit suite and the browser files (the factory's
build step runs them); main has not moved since the clone, so the merge of main is a no-op.
