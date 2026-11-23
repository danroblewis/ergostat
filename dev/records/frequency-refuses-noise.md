# frequency-refuses-noise: a frequency response from data is not drawn when the data cannot support one

Found 2026-11-23: the server computes a correct per-frequency coherence floor, but `ergostat/web/static/plots-freq.js` ignores it and uses a fixed 0.6, so unrelated noise passes. A per-frequency floor alone is also not enough: in a check, 98% of 1,024-sample noise records had some frequency above it.

See `docs/research/2026-11-23-charts/catalog.md`, item B2 and guardrail G5.

Change.
- The panel uses the server's floor, and the fixed 0.6 is removed.
- The server applies a correction across frequencies and decides, per guardrail G5, whether the record supports a response at all.
- When it does not, the panel says this data cannot support a frequency response and why, and draws no curve as if it were one.
- The default dashboard stops presenting arrivals against completions as a working Bode or Nyquist example.

Definition of done.
1. Uncorrelated input and output are refused in at least 95% of generated records, at the default settings.
2. A known first-order system with a real excitation is still drawn, with gain and phase within the stated tolerance.
3. The decision is made on the server and tested there; the page only shows it.
