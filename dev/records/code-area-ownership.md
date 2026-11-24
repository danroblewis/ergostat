# code-area-ownership: Areas of the code have owners, and work is routed to avoid collisions

Map code areas to owning streams (a milestone, a worker kind, or a single lane at a time), declared in the model. Gaps touching the same hot area are sequenced or batched together instead of colliding in the queue. Use the conflict history to draw the first map.
Done: 1. A map from the record's conflict history. 2. A replay shows fewer conflict send-backs. 3. The map is data the owner can change.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.
