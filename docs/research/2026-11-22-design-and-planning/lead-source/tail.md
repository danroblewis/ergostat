## 4. What to keep

Named by several designers, and to be protected while the changes above are made.

- **The leaf notation of both diagrams.** Dynamics: stocks, double pipes, bow-tie valves, clouds, signed connectors, R and B markers with direction, `<shadow>` variables, and the desired → gap structure where it is drawn (`sdxb-8797-api.png`, `ixdb-sf-dynamics-delivery.png`). Blocks: signed summing junctions, r/e/u/y/d, H on the return, P(s) = 1/s for a stock, relay and dead-band glyphs, C(z) with sampler and hold, MIMO bars with widths, off-page pills (`ceb-is-service-into.png`, `ixdb-sf-blocks-delivery.png`). Monochrome and shape-coded.
- **The evidence panel for a goal.** y with r, u and e on one time axis, off periods shaded, crossings, decisions folded "alike when only their numbers differ", "typically holds again 30s after". An SRE called it a better incident view of one SLO than any dashboard they own (`sreb-job-loop-panel.png`, `infod-tf-loop-click.png`).
- **Loop tracing.** Clicking an R or B marker dims the rest and lights the path, with the "Around the loop" table (`ixd-tf-into-click-loop.png`); hover dims what is not connected; selection is shared between views.
- **The stock panel.** Its causes strip (level with its desired level, inflow and outflow on one axis, replay dashed, projection with its fan), the typeset equation, parameters with units, and "Show them on the Items page" (`sdxb-8796-users.png`, `pmb-sf-users-stock.png`).
- **The controller and process panels' substance.** K ± σ, θ ± σ, residual whiteness, independence from u, the closed-loop data caveat, the refusal to propose a model the data cannot support, the sized step test, the transfer matrix with structural zeros; real MathML (`ceb-is-process-panel.png`, `a11yb-8793-deadband-panel.png`).
- **The honest modelling prose.** "Not exercised by the record: not evidence it is absent", identifiability against time constants, the stock-against-flows balance check. Reword it; do not remove it.
- **The Guide.** Its structure (why, what is, what we control, yours) and above all frame 2, the same loop drawn both ways under "System dynamics draws what is; control draws what we control" (`ceb-guide-1.png`). It is the clearest statement of the product.
- **The software-factory top level.** Two systems with signed links between them: the model every folded home should follow (`story-1-b3-home.png`).
- **The Loops table's columns** (now, bound, error, time off, back in, trend, behaviour): they are the rows the boxes should carry.
- **Items that already read well.** The roadmap's Graph (critical path, what waits, who works on what) and Timeline (`pm-road-graph.png`), image-squeeze's two-state cases chart, the process map with its rework mark, and the item page's Relations.
- **The per-view wording of the side list** (desired and gap in Dynamics, setpoint and error in Blocks). Keep the idea; fix its edges (Q23, Q46, Q62).
- **The shell.** Quiet type, one ink with red only for off, complete dark mode, a visible focus ring on native controls, Escape closing the panel, `prefers-reduced-motion`, landmarks, breadcrumbs, an address per view, "More beyond the edge" in place of shrinking, the time-window menu, the project switcher's counts, the weekly tally per class of action, and the JSON API.

## 5. Left out, and why

- **A text view of the diagram, a hover glossary, a first-visit banner, an Inbox page.** Each is a new surface. The caption (Q02), the view labels (Q03), the keyboard path through the diagram (R9) and the header link (Q43) do the same work inside what exists.
- **Status colour on Blocks' lines.** Blocks stays monochrome; status is a word and a bold e (R4).
- **A confirm dialog on every Approve.** A list that holds still, buttons named for what they answer and a confirmation in place (Q47 to Q49) remove the mis-click without a dialog. Revisit if real approvals show mis-clicks.
- **Prometheus exposition and an Alertmanager channel** (the SRE's "feed the tools that page me"). Right for the intent, but not a page design matter; passed on as a product note.
- **`model-error` as an auxiliary instead of a stock, shadow-variable style, the biflow arrowheads.** Modelling choices in the template, with no cost to a reader today.
- **Shared scales on the Loops sparklines, the system picker's styling, the Guide's first slide.** Taste, or superseded by R1.
