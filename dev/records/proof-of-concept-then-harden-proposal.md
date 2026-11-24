# proof-of-concept-then-harden-proposal: Proposal: land a proof of concept early, harden it in follow-up gaps, revert it if it breaks

depends-on: [merge-first-verify-after-proposal]

The owner asked what this would look like: do we keep the spike on main, how do we make sure it is rebuilt, does it have a time limit, could scheduled bisection revert it. Write docs/proposals/proof-of-concept-then-harden.md.
Settle: 1. A gap chain: proof of concept (behind a flag, light checks), then hardening gaps created automatically. 2. A time limit on main before it must be hardened or is removed. 3. Scheduled bisection and revert of unverified work, and what happens to later work that depends on it. 4. Cost against building it properly once, from the record. 5. The build split.
Done: all five settled, with one worked example from recent gaps.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.

## Where it stopped

Round 1: written. docs/proposals/proof-of-concept-then-harden.md settles the five, each in its own section:

1. The chain (§1). A gap with `proof: NAME` lands behind an off flag, after program and rule checks only (the flag,
   at most 40 changed lines in files already on main, tests that always run, a `## Hardening` list). On landing, a
   program block opens two gaps: a hardening review of the proof's diff, then `-hardened`, which fixes the findings
   and removes the flag. Core gets two declared options: `proofs:` and `most_in_state`.
2. The time limit (§2). 72 h from the proof's merge (`proof-hours`, ceiling 336). The pipeline manager is triggered
   at 48 h. At the limit the proof and its landed chain are reverted through verify.py's revert. The owner can extend
   it once. When the time cannot be read, an intervention is raised and nothing is reverted.
3. Bisection and revert (§3). A proof's landing makes the verification lane due at once. Its dependents are its
   chain and the gaps that declare it. A rule bars any other gap from using a proof while it is `proven`.
4. Cost (§4). This is from the record, with ceilings and not spend, since the clone holds no `ai_cost_usd`. There is
   no saving on work that is kept ($60 either way in the example). The saving is on work that is dropped (about $15
   against up to $52). The proposal recommends an opt-in path for exploratory gaps.
5. The build split (§5). Gaps 0 to 4, about 670 lines in all.

The worked example (§6) is merge-first-verify-after, with times from git, lines from `git log --shortstat`, and
findings from its record. The control-spike episode from the same record is the evidence behind the tests-run-always
rule.

Choices taken alone, the reversible ones:

- The path is opt-in per gap, and the proposal recommends it only for exploratory gaps. That follows the record and
  is one of the two questions put to the owner.
- The AI review is moved into the chain, not dropped. In the example, the implementor's own list of what was left
  shared none of the six findings the reviews raised.

A finding for the gap this one depends on (not fixed here, lesson-13). `verify.stacked()` treats any later merge
whose branch holds the culprit's tip as stacked. So a gap that merged main after the culprit landed would be reverted
with it. This is a reading of dev/bin/verify.py and was not run. The proposal makes it gap 0: either
merge-first-verify-after takes it as a finding, or it becomes its own gap before the proof path is switched on.

Nothing in the live instance was read or changed. Size: 0 net lines outside tests/, docs/ and dev/.

Round 2: the two blocking findings of the review are answered, and both are in the proposal's text.

- The clock restarted at each landing, so a proof that kept breaking main never expired (§2 against §1c and §3a).
  Settled: the clock runs from the proof's **first** `gap.merged`, chosen by `seq`, and never restarts. Core's option is
  now `clock_from: [STATE]` on a kind, which gives `hours_since.STATE` from the first move into the state (lowest
  `seq`). The reading is kept after the item leaves the state and is absent, not 0, for an item never in it. This
  replaces round 1's `most_in_state` (above, in round 1's summary). §3a now says the clock keeps running from the
  first landing. Round 1's line "its clock starts again from that merge" is removed. A proof reverted at its limit
  no longer lands again as a proof: the owner has it rebuilt as an ordinary gap, or continues its chain.
- One kind-wide duration could not express a 48 h trigger, a 72 h revert and a per-proof extension (§1c against §2).
  Settled: core holds no limit. Each proof carries `proof_limit_hours` (written by the queue with its first merge)
  and `proof_extended_hours` (written once by `proof-extend`). The factory's block `proof-clock` works out
  `limit = base + extension` and `due = limit - base/3`, so 48/72 h unextended and 120/144 h extended. It raises
  `proof-due` once per limit and reverts at the limit only after reading again inside the lane's lock, so an
  extension answered in between wins (lesson-1). An absent clock, or a field that is absent or not a number,
  raises an intervention and reverts nothing (lesson-3). §5's gaps 1 and 3 are rewritten to match, with tests named
  for each of these cases. The total stays at about 670 lines.

Choices taken alone, the reversible ones: the limit fields sit on the item, so a later change to `proof-hours` does
not move a running proof's limit. The extension is a field the owner can still answer while the proof is under its
limit, and it is refused once the proof is `expired`.

No other findings were raised in round 1's review. Nothing in the live instance was read or changed. Size: 0 net
lines outside tests/, docs/ and dev/. No tests were run, since the branch changes only docs/ and dev/records/.
