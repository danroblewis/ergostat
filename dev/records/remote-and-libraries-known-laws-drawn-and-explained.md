# remote-and-libraries-known-laws-drawn-and-explained: A declared law is drawn as its block's function in Blocks and said in words by explain

depends-on: [remote-and-libraries-known-controller-laws]

Problem: after known-controller-laws a declared law is in the IR but the Blocks view still draws an external block as an unknown function and explain says nothing of it. Change: ergostat/blockdiagram.py draws the declared law as the block's function, in the block diagram's own notation, marked 'declared kubernetes-hpa' (or 'declared alert-rule'), where an identified law is marked identified today; no new panel or element kind. ergostat/spec/explain.py says the law in words with its parameters ('scales to ceil(replicas x utilisation / 0.6), within 2..10, down only after 5m'). AGENT-GUIDE says when to declare a law and that a declared law is an assumption until tested against the record. Done: the Blocks answer for a block with `law:` carries the function and its mark; a block without one is drawn exactly as today (golden); the MCP explain tool returns the same words; the browser test for the Blocks view passes with one fixture using a declared law. Files: ergostat/blockdiagram.py, ergostat/spec/explain.py, docs/AGENT-GUIDE.md, tests/test_known_laws.py (three tests). Budget: 70 net lines.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1; nothing left. About 32 net lines outside tests and docs, within the 70 budget. Choices made with
nobody to ask (each the most reversible one):

- Two files outside the Files list. ergostat/web/static/blocks.js changes one line so the page writes the node's
  `declared` mark where it writes "identified" today; without it, the Blocks answer would carry the mark but the page
  would not draw it. docs/SPEC.md §12d's sentence "not yet drawn, explained..." is now current.
- The browser test is the third test in tests/test_known_laws.py, not a new example under examples/ (a new example
  would go through every browser test and demo_check). It serves ticket-factory's copy with its model replaced by the
  test's HPA model, draws Blocks, and runs the Blocks view's own audit (AUDIT, BLOCKS_DOM from test_diagram_rendering).
  It needs Playwright: in a unit run without it, that test is skipped.
- When the record also identifies a law for the block, the identified law is drawn (evidence over assumption) and the
  declared one stays in the block's rows. Swapping the order would be a one-line change.
- The golden is a sha256 of the whole Blocks answer for the no-law model, taken from this branch's base before any change.
