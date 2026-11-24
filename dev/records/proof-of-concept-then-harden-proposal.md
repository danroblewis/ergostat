# proof-of-concept-then-harden-proposal: Proposal: land a proof of concept early, harden it in follow-up gaps, revert it if it breaks

depends-on: [merge-first-verify-after-proposal]

The owner asked what this would look like: do we keep the spike on main, how do we make sure it is rebuilt, does it have a time limit, could scheduled bisection revert it. Write docs/proposals/proof-of-concept-then-harden.md.
Settle: 1. A gap chain: proof of concept (behind a flag, light checks), then hardening gaps created automatically. 2. A time limit on main before it must be hardened or is removed. 3. Scheduled bisection and revert of unverified work, and what happens to later work that depends on it. 4. Cost against building it properly once, from the record. 5. The build split.
Done: all five settled, with one worked example from recent gaps.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.
