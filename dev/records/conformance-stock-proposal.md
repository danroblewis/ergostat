# conformance-stock-proposal: a reviewed proposal for counting "features we wish we had" as a stock

depends-on: []

The owner, 2026-11-21: for any application we can list the features we wish we had (supported file formats, algorithms, diagram types), test each, and count how many pass, like a Jenkins graph of passing tests. That count, as a stock, would be the signal for feedback loops that raise it.

## Definition of done
1. `docs/proposals/conformance-stock.md`, written for the owner: how a conformance list is declared, how its cases are run and counted, how the count becomes a stock with its own sensor and history, how a loop's goal reads it, and how it differs from the unit suite (a failing case is expected and counted, never a red build).
2. A worked first list for ergostat itself, chosen from what the repo already shows it wants (diagram types in `docs/proposals/diagram-options.md`, model formats, discovery algorithms), with each case named and today's expected result.
3. A milestone: an ordered list of gaps, each with a one-paragraph definition.
4. Every claim about today's code cites file:line on main. No code changes.

## Files to touch
`docs/proposals/conformance-stock.md` only.

## Size budget
0 lines of code; the proposal under 500 lines.
