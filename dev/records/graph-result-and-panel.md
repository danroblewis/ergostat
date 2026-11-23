# graph-result-and-panel: `graph`, the three producers adapted, named kinds, ELK in a worker, budgets and aggregation, matrix fallback

depends-on: [fix-process-rework-flag, result-frames-and-verdicts]

From the chart catalog, `docs/research/2026-11-23-charts/catalog.md`: read section 7 for this item, and the sections it cites (result shapes in section 2, guardrails in section 6, workflows in section 5, and the source reports beside it).

The owner's decisions (2026-11-23): data sources are like Grafana's, each with its own text language; PromQL is primary and read-only SQL is only for what PromQL cannot do; metrics hold aggregates over bounded labels and anything with a generated ID stays in the event log; stocks are gauges, flows are counters, delays are histograms; no visual query builder; result shapes decide which charts apply. VictoriaMetrics is the default metrics store for new installs. Rework means an item repeated a step. The new diagram kinds named in the catalog are allowed (update `docs/proposals/diagram-options.md`), limited to those named kinds. The service map is built from caller and callee labels in metrics first. No new pages: charts are Dashboard panels or live on existing pages, and the Blocks and Dynamics views stay separate and true to their disciplines.

This is item B6.

Delivers: `graph`, the three producers adapted, named kinds, ELK in a worker, budgets and aggregation, matrix fallback

Unlocks charts: 74, 75, 77 (section 3.2).

Definition of done.
1. Everything this item delivers in the catalog works on a hand-worked record, with its numbers checked by a test.
2. Each guardrail the catalog assigns to this item refuses or warns as stated, with a test that tries the misuse.
3. A chart that cannot be trusted on its data says so, and does not draw as if it could.
4. Decision logic is in pure functions with fast in-memory tests. Anything the catalog marks `[unsure]` is measured or left visibly unsure, never assumed.
5. It works at factory size within the budgets the catalog states, and reads neither the event log per request nor a raw internal table from the page.
