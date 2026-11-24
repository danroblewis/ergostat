# A proof of concept on main, hardened after, reverted if it breaks or is left

The owner asked what this would look like: do we keep the spike on main, how do we make sure it is rebuilt, does it
have a time limit, could scheduled bisection revert it. The owner's decisions behind it (2026-11-23): more delivered
work per AI dollar; tests exist for regressions; program and rule checks are preferred over AI review; any path that
checks less before merge needs a way to find and revert regressions on main.

The proposal in one line: **a gap may be declared a proof: it lands behind a flag that is off, after program checks
only, and on landing it opens its own hardening gaps. If they are not all merged within a time limit, the proof is
reverted. The verification lane of merge-first-verify-after finds and reverts it, like any merge, if it turns main
red.** It is off unless a model declares it. This factory is the first user.

The record does not support the hope that this saves money on work that is kept (section 4 and the worked example in
section 6). It saves money on work that is **dropped** after the proof shows it is not worth keeping. So the
recommendation is an opt-in path for exploratory gaps, not a default for every gap.

Words: core text says *item*, *state* and *proof* (ergostat ships no unit of work, CLAUDE.md invariant 1). In the
factory, a proof is a gap and so is each hardening step.

## Where the numbers come from

The live instance was not read or changed (the owner's boundary). Every number here comes from this clone and says
which source it is from:

- **git history**: commit times, and lines per commit (`git log --shortstat`). Times are in UTC unless marked.
- **the gaps' records** (`dev/records/*.md`): what each round found and changed.
- **docs/proposals/review-at-the-feature.md**: its count of rounds over 320 records. Rounds 2, 3, 4 and 5+ are
  mentioned in 72%, 42%, 26% and 19% of them, which is about 2.6 review sessions a gap as an upper bound. It also
  counts merges per day: 198 on 2026-11-23.
- **dev/factory.toml**: the session caps. Implementor $15, reviewer $5.

The clone does not hold each session's real cost (`ai_cost_usd`). Costs below are therefore **ceilings** (sessions
times caps), not spend.

## 1. The gap chain: a proof, then hardening gaps made for it

### 1a. What a proof is, and its checks

A gap whose definition carries `proof: NAME` is a proof. Its branch must meet these rules, each one a program or a
rule, with no AI:

| Check | A proof, before main | A hardening gap, before main | An ordinary gap (today) |
|---|---|---|---|
| ruff, imports | yes | yes | yes |
| its own tests and the smoke set (`verify.quick`) | yes | yes | yes, then full suites when `[verify] after` is off |
| **flag rule**: a flag named NAME exists and is off by default | yes | n/a | n/a |
| **hook rule**: lines changed in files that already exist on main ≤ `hook_lines` (40); everything else in new files | yes | no | no |
| **tests run always**: its tests are in the unit suite and turn the flag on themselves; none runs only when named | yes | yes | yes |
| **Hardening list**: its definition has a `## Hardening` section with 1 to 5 items, each naming an acceptance test | yes | n/a | n/a |
| size budget, strays, definition of done | yes | yes | yes |
| AI review | **no** | yes | yes |
| full suites | after landing, by the verification lane (section 3) | the same | the same, with the lane on |

Why each rule:

- **The flag rule** keeps the proof's behaviour off on main. Off is not the same as absent, though. In the worked
  example, `verify.py`'s `reapplied()` and `taken_out()` are read by `queue.py` even with `[verify] after = false`
  (the module's own docstring says so). That is why there is a hook rule as well.
- **The hook rule** keeps the proof's code that runs while the flag is off small enough to read, and easy to revert.
  A proof made mostly of new files reverts without conflicts, even when later merges touched the same files.
  `hook_lines` has a ceiling of 200 (lesson-4). A diff that cannot be read counts as over the limit (lesson-3).
- **Tests run always** comes from the record's one case of a spike kept on main. `tests/test_control_spike.py`
  (5981d76e, from control-aware-estimates-proposal, which landed at 01:06 UTC on 2026-11-24) ran only when named.
  When a gate's rerun named it, it failed with `AttributeError: 'Shadow' object has no attribute 'per'`.
  `closedloop.Shadow` borrows `Engine.goals`, which reads `self.per` for goals held per item, and the factory's own
  model holds such a goal. That is an ergostat defect that no suite showed. It surfaced at whatever moment a gate
  named the test, and was blamed on whatever was being checked then. It cost:
  - two interventions (main-broken-b9341591cb70 and -fa51005d0951);
  - forecast-promise-proposal held in fix;
  - the-control-spike-s-gate-cost to repair it (merged at 03:08 UTC);
  - main-broken-needs-the-test-on-main, because the check had blamed main for a test main did not yet hold.

  A proof whose tests run in every unit suite shows such a failure in the first verification after it, and the merge
  that made it is blamed, as for any regression.
- **The Hardening list** comes from the proof's own implementor, and it is not enough by itself (section 6: in the
  example, none of the six findings that review raised were on the implementor's list of what was left). So the
  chain always begins with a review of the proof's diff, below.

### 1b. The hardening gaps, made when the proof lands

When the queue lands a proof (`gap.merged` with `proof`), a program block, `harden-open` (no AI), opens its chain.
The chain is ordinary gaps, related to the proof by the group relation
`hardens: {kind: gap, group: true, precedence: false}`, so the proof's row on the Items page shows them as members,
done of total (SPEC §5a, *Progress per group*; nothing new in core):

1. **`<proof>-hardening-review`**: one reviewer session ($5 cap), the reviewer's brief and the review lessons,
   reading the proof's whole diff on main. Its output is not a verdict. It is a list of findings, each turned into a
   numbered item of the next gap's definition of done. This is where the AI review the proof skipped happens, once,
   over code that no longer changes under it.
2. **`<proof>-hardened`**: one implementor gap. Its definition of done is the Hardening list plus the review's
   findings, each with a test the implementor shows failing first. It is reviewed as any gap. It ends by **removing
   the flag**: the proof's code paths become unconditional, which makes this the step that turns the work on.
   Removing the flag is rule-checked, and the queue refuses the gap while NAME is still declared anywhere.

Two gaps, not one per finding. More gaps mean more queue landings and verifications per proof. In the example, the
findings of round 2 needed one fix session between them (e2efacf3).

Turning the flag on on the live instance stays the coordinator's job, as every live change is.

### 1c. What core gets: two options a model declares

The owner's rule: general parts go in core, off unless declared, naming no gaps or software.

- **`proofs:`**, a top-level list in a model. Core code that is itself a proof reads `model.proof("NAME")`, which is
  false unless the model lists NAME. The names a build knows are an allowlist in `ergostat/proofs.py`. `check`
  refuses a name not in it (`unknown-proof`), a name listed twice, and anything that is not a list of strings
  (`bad-proofs`, refused at the key and never read as empty, lesson-3). A proof removed from the allowlist by its
  hardening gap gives `proof-hardened` (a note, not a refusal), so a model that still names it keeps working.
- **`clock_from`** on a kind: a list of states, at most 8. For each listed STATE, every item that has ever moved into
  it gets the reading `hours_since.STATE`: the hours from its **first** move into STATE to now. The first move is the
  one with the lowest record `seq`, not the earliest stamp (lesson-2); only the hours are taken from that event's
  stamp. The clock does not restart when the item leaves the state and comes back, and it keeps counting after the
  item leaves. An item never in STATE has no reading (absent, never 0, lesson-3). Core sets no limit and acts on
  nothing: the reading is a number a goal or a block may compare against whatever it likes. `check` refuses a state the
  kind lacks, a list over 8, a state listed twice, and a value that is not a list of state names (`bad-clock-from`,
  refused at the key, never read as empty). It is general: any model may ask how long an item has been under way
  since it first reached a state.

  Core deliberately does not hold the limit. One kind-wide duration gives one threshold per state, and the factory
  needs three per item (a trigger, a limit, and a limit that one item's extension changes, section 2). Limits per item
  are the model's own fields, compared by the model's own block.

Everything else is the factory's: what a proof is, the checks, the chain and the revert. Core never knows about git.

## 2. The time limit on main

**Settled: 72 hours from the proof's first merge on main to the merge of its last hardening gap**. This is the
factory's model parameter `proof-hours`, with a ceiling of 336 (lesson-4). A landed proof moves to the state `proven`
and leaves it for `merged` when its chain is merged.

**The clock.** It starts at the proof's **first** `gap.merged`, chosen by `seq`, and never restarts. It is read from
core's `clock_from: [proven]` on the gap kind (1c) as `hours_since.proven`. A proof that breaks main, is reverted, goes
back to fix and lands again moves into `proven` a second time, but its clock still counts from the first landing. So a
proof that keeps breaking main runs out of time, which is the point of the limit.

**The limits, per proof.** Each proof carries two fields of its own, written by the factory and never by core:

| Field | Written by | Value |
|---|---|---|
| `proof_limit_hours` | the queue, in the same write as the proof's first `gap.merged` | `proof-hours` as it is then (72) |
| `proof_extended_hours` | the inbox's `proof-extend` answer, once | 1 to 72; absent until extended |

The factory's program block `proof-clock` (no AI) runs on the pipeline's beat. It looks at each gap that has an
`hours_since.proven` reading (it has landed as a proof at least once) and is not yet `merged`, `parked` or `dropped`.
That includes a proof sent back to fix after a red run. For each, it reads `hours_since.proven` and the two fields, and
works out:

- `limit = proof_limit_hours + proof_extended_hours` (the second counted as 0 only when absent; present and not a
  number is unreadable);
- `due = limit - proof_limit_hours / 3`, so 48 h for an unextended proof and 120 h after a full extension.

Keeping `proof_limit_hours` on the item means that changing `proof-hours` in the model later does not move a running
proof's limit.

Why 72 h:

- A chain is two gaps one after the other. In the record, an ordinary gap goes from definition to landing in about
  4 h (agent-show-page: definition at 02:09, landed at 06:14) when its review passes at round 2. A chain of two gaps
  with a round or two each fits within a day. 72 h allows three times that, for parked machine time and the owner's
  sleep.
- Main moves fast: 198 merges on 2026-11-23. Each merge is a chance for unreviewed code to meet something it was not
  built for, as the control spike's test did. With the tests-run-always rule, catching breakage is the verification
  lane's job, so the limit's job is ownership: unhardened code does not stay on main with nobody building on it.

What happens at the limit:

- **At `due` (48 h unextended)**, `proof-clock` triggers the pipeline manager with `proof-due`. It may move the chain
  up, ask the owner, or do nothing. The trigger is keyed by the proof and the `limit` it was raised for, so it fires
  once per limit: an extension raises a new `proof-due` at the new `due`, and a later beat does not raise the same
  one again (lesson-5).
- **At `limit` (72 h unextended) with the chain not all merged**, `proof-clock` reverts the proof and every hardening
  gap that has landed. It uses the verification lane's revert (section 3), so the same `Reverted-tip:` commits are
  made, under the same lock, through the same gated push. Inside that lock, before reverting, it reads the item's
  fields and `hours_since.proven` again and reverts only if they still say the limit has passed, so an extension
  answered between the beat's read and the revert wins (lesson-1). A proof that is already off main at its limit,
  having been reverted by a red run and not yet landed again (`taken_out()`), has nothing of its own to revert. Its
  landed hardening gaps, if any, are reverted as above. The proof gap is parked with the reason `expired`. Its open
  hardening gaps are parked too, not dropped, so the chain can be continued.
- **Extending.** The owner may extend the limit once, by 1 to 72 h, through the inbox (`proof-extend`). The answer
  writes `proof_extended_hours` under the same lock as the revert, and is refused if the field is already present (a
  second extension) or the proof is already `expired`. A proof the owner wants to keep longer must be hardened, or
  rebuilt later as an ordinary gap.
- **Unreadable.** A proof whose `hours_since.proven` is absent, whose `proof_limit_hours` is absent, not a number or
  over the ceiling, or whose `proof_extended_hours` is present but not a number from 1 to 72, or whose chain cannot be
  read, is neither passed nor reverted. It raises an intervention (lesson-3: never fine). A revert is reversible
  (`verify.reapplied()` brings a reverted gap back whole), but it is not made on a guess.

**Coming back.** A proof reverted because it broke main (section 3a) goes back to fix and lands again through
`reapplied()`. Its clock keeps counting from the first landing. A proof reverted at its limit does **not** land again
as a proof: if its clock were kept it would be expired again at once, and if it were restarted the limit would mean
nothing. The owner may have it rebuilt as an ordinary gap (a new definition without `proof:`, the full review before
main), or continue its parked chain, whose `-hardened` gap then takes the proof's diff in with its own.

## 3. Scheduled bisection and revert, and work that depends on a proof

### 3a. Finding a proof that breaks main

This uses the lane of merge-first-verify-after (`dev/bin/verify.py`) unchanged, with one addition. **A proof's
landing makes the lane due at once** (the same as `again` after a revert). The proof skipped the AI review, so the
lane verifies it on its next 10-minute turn, in a short window. A short window means a cheap bisection: a window of
one or two merges is settled in one round of `first_red`, not the several that a 1,500-line window can take.

Red and the proof is the culprit: it is reverted with its dependents (3b) and goes back to fix with the failing
tests, as any culprit does (`gap.queue-failed`). Its clock keeps running from its first landing (section 2: it is
read from the first move into `proven` by `seq`, which a second landing does not restart). The time limit is for the
whole chain, so a proof that keeps breaking main runs out of time.

Red and a later merge broke the proof's tests: that merge is the culprit and is reverted, as for any regression. The
proof's tests are main's tests once it has landed (the owner: tests exist for regressions). This is what the control
spike lacked.

### 3b. Later work that depends on the proof

Work on main can depend on a proof in three ways. Each has its own answer:

1. **Its hardening gaps** (`hardens`). They are reverted with the proof and given back as stacked gaps are today
   (`gap.retried`, back to approved, uncounted). When the proof comes back, `reapplied()` brings them back whole.
   Hardening gaps not yet landed wait: their `depends-on` on the proof is unmet while `taken_out()` says the proof is
   off main.
2. **Gaps that declare a dependency** on the proof (`depends-on`, `stacked_on`). The same as 1.
3. **Anything else.** Settled by a rule, so it cannot happen: **while a proof is `proven`, no gap outside its chain
   may name its flag or import its new modules**. This is a program check on every gap's diff (an allowlist of the
   chain's gaps per proof, lesson-8). A gap that needs the proof waits for `<proof>-hardened`, or joins the chain by
   declaring `depends-on`. This is what keeps a revert to the proof's own files and the chain's, and the hook rule
   (1a) keeps those few.

**A finding in the lane this builds on (not fixed here, lesson-13).** `verify.stacked()` takes as stacked every later
merge whose branch holds the culprit's branch tip
(`merge-base --is-ancestor c.parents[1] x.parents[1]`). Every gap merges main before it is called built. So a gap
that merges main after the culprit landed, and lands later in the same window, holds the culprit's tip, and would be
reverted with it as if it were stacked, even when it has no relation to the culprit. The fixture in
`tests/test_verify_after.py` lands x, a, b and c in one batch, all branched before a landed, so it never sees this.
This is a reading of the code and was not run here. A proof makes the lane due at once and keeps windows short, which
makes the case rarer, not impossible. **Before the proof path is switched on, the lane must take dependents from the
declared relations** (`stacked_on`, `depends-on`, `hardens`), not from ancestry. That is either a finding for
merge-first-verify-after's next round, or a gap of its own (section 5, gap 0).

### 3c. Reverting at the time limit

A revert at the time limit is the same revert, made by `proof-clock` instead of by a red run. Its commits carry
`Expired: gap/NAME` instead of `Failing:`. `escapes.py` counts it as no escape (main was not red), the same way it
skips `Stacked-on:`. After it, the lane verifies again (`again`), as after any revert.

## 4. Cost against building it properly once, from the record

**What a proof saves when it is kept.** Very little, and maybe nothing. The proof skips the AI review before main,
but the chain has the same review later, over the same diff and with the same lessons, so it finds the same defects
and needs the same fix sessions. Section 6 works it through on a real gap: $60 at the ceilings either way. The chain
also adds one queue landing and one verification per proof (two gaps where there was one), and the rule checks.

**What a proof saves when it is dropped.** Everything after the first session. On the record's mentions, an ordinary
gap that lands has up to 2.6 review sessions and 1.6 fix sessions, a ceiling of about 2.6 × $5 + 2.6 × $15 = $52. A
proof costs 1 implementor session ($15) and one queue landing, and if the owner, having seen it work on main, decides
not to keep it, the time limit removes it at no further AI cost. The gap the record has like this is
control-aware-estimates-proposal: a spike, one session, after which the proposal recommended **not** coupling. The
build gap was amended to something smaller instead of building the coupling and hardening it.

**What a proof costs that building once does not.**

- Code on main that is not reviewed, for up to 72 h (144 h with the one extension). The control spike's named-only test cost two follow-up gaps
  (ceiling $20 each), a fix round for a gap it held (forecast-promise-proposal, up to $20) and two interventions for
  the coordinator. The tests-run-always rule is meant to turn that into one verification that blames the right merge.
- The rule checks and the chain's blocks to maintain (section 5).
- Reverts. A proof reverted at the limit costs its sessions and nothing on main. Its dependents are only the chain,
  by rule 3b.3.

**How the switch is judged.** These are readings the factory has or that are added in section 5, compared over proofs
against ordinary gaps of the same size class:

- AI cost per merged net line (`ai_cost_usd` over `net_lines`, the chain counted as one);
- `proofs-dropped` against `proofs-hardened`, and the AI cost saved on those dropped (the proof's session against the
  median ordinary gap's of its class);
- `proofs-expired` and `proofs-reverted`;
- `verify-escapes` caused by a proof;
- `lessons-recurring` in the chain's reviews.

If proofs are almost never dropped, the path pays nothing and should be switched off.

## 5. The build split

Each item below is a gap. All are off until declared, and switching them on is the coordinator's job.

0. **verify-dependents-by-declaration** (dev/bin, about 60 lines): `verify.stacked()` and `revert()` take dependents
   from `stacked_on`, `depends-on` and `hardens`, not from branch ancestry, with a test in which a gap merges main
   after the culprit landed and stays on main (section 3b). This is needed before anything below. If
   merge-first-verify-after's review takes it as a finding, this gap is not needed.
1. **core-clock-from** (ergostat/, about 90 lines plus tests): `clock_from` on a kind, the reading `hours_since.STATE`
   in the Items API and on the item's row, the `check` refusals, and SPEC §5a. Tests: the first move is chosen by
   `seq` and not by stamps (a later event with an earlier stamp does not move it); leaving the state and coming back
   does not restart the clock; an item never in the state has no reading; each refusal; a list of 8 and of 9.
2. **core-proofs-option** (ergostat/, about 80 lines plus tests): the `proofs:` key, `model.proof()`, the allowlist in
   `ergostat/proofs.py` (empty when it lands), the `check` refusals and the `proof-hardened` note, SPEC.
3. **factory-proof-path** (dev/bin and dev/model, about 380 lines plus tests):
   - `proof:` in a definition, and the state `proven`, the relation `hardens` and `clock_from: [proven]` on the gap
     kind;
   - the rule checks of 1a and 3b.3 in the implementor's and the queue's checks (the flag, the hook lines, tests run
     always, the Hardening list, nothing outside the chain using a proven proof);
   - the queue landing a proof on `verify.quick`, writing `proof_limit_hours` with its first `gap.merged`, and making
     the lane due at once;
   - the block `harden-open`, and the block `proof-clock`: `due` and `limit` per proof from its fields, the
     `proof-due` trigger once per limit, and the revert at the limit (through `verify.revert`, `Expired:`) after
     reading again inside the lane's lock;
   - the inbox's `proof-extend`, writing `proof_extended_hours` once, under the same lock;
   - `[proofs] hook_lines` in dev/factory.toml, and `proof-hours` in dev/model/landing.yaml.

   Tests on the fixture repo: a proof lands with no AI review and its chain is opened; one over the hook lines is
   refused; a proof that is reverted as a culprit and lands again keeps its first clock and is reverted at 72 h from
   its first landing; `proof-due` is raised at 48 h and not again at the next beat; an extended proof (+72 h) is not
   reverted at 72 h, gets `proof-due` at 120 h and is reverted at 144 h; a second extension is refused; an extension
   answered between the beat's read and the revert stops the revert (the competing write put in that gap); a proof
   expired at the limit is reverted with its landed hardening gap and is not landed again as a proof; a gap outside
   the chain using the proof's module is refused; an absent clock, an absent or non-number `proof_limit_hours`, and a
   non-number `proof_extended_hours` each raise an intervention and revert nothing.
4. **proof-measures** (dev/model/measures.yaml and dev/bin/measure.py, about 60 lines): `proofs-hardened`,
   `proofs-dropped`, `proofs-expired`, `proofs-reverted`, and the chain's AI cost per merged net line (section 4).

These come to about 670 lines, more than one gap's budget of 600, so they are split as above. Gap 0 comes first. Gaps
1 and 2 can be built side by side. Gap 3 needs 0, 1 and 2, and gap 4 needs 3.

## 6. Worked example: merge-first-verify-after

This was chosen because it was built much like a proof: its first round shipped everything behind a flag that is off
(`[verify] after = false`), and its later rounds were hardening. Times are from git and lines from
`git log --shortstat` over dev/bin, dev/model and dev/factory.toml. Rounds and findings are from its record.

**As it happened (one gap, reviewed before main).**

| Step | When (UTC, 2026-11-24) | What | Net lines |
|---|---|---|---|
| Definition | 07:22 | | |
| Round 1 built | 07:41 to 07:59 | `verify.py`, hooks in `queue.py`, `halves.py`, `upgrade.py`, `measure.py`, the model's parameters | +731 |
| Review 1 | by 08:32 | 5 blocking findings: main's own failure on the full-run path (lesson-3, -10); a stacked gap landing during verification (lesson-1); outcomes said before the push settled; no load interlock (lesson-4, -8); false escapes (lesson-7) | |
| Round 2 | 08:32 | all five fixed in one commit (e2efacf3) | +103 |
| Review 2 | by 08:57 | 1 blocking finding: a push denied at once erased the hold (lesson-1, -3) | |
| Round 3 | 08:57 | fixed (15571de0) | +1 |

Its sessions: 3 implementor sessions and 3 reviews, assuming round 3's review approves (that review is not in the
clone). The ceiling is 3 × $15 + 3 × $5 = **$60**. It is not on main as of this clone. This gap is built on it.

**As a proof.** Round 1 passes the rule checks except one. Its hooks in files that already exist on main are 89
changed lines in four dev/bin files (`queue.py` 40, `halves.py` 24, `upgrade.py` 14, `measure.py` 11), plus 51 in
dev/factory.toml and the model. That is over `hook_lines` (40), which counts code. The implementor would either move `reapplied()`'s call site behind the flag
or say why (as an overrun). It lands on the quick check at the next queue run, and the lane verifies it alone on its
next turn.

Then `harden-open` opens the chain. The proof's own list of what was left (round 1's "Left for the coordinator":
switch-over, lint, the git version, the smoke set's time) shares **none** of the six findings the reviews raised. All
six come from the hardening review. Assuming it finds the five that review 1 found, `-hardened` fixes them (round 2's
work) and its review finds the sixth (review 2's), so a fix round follows (round 3's).

| Way | Implementor sessions | Reviews | Ceiling | Queue landings | Code on main first | All of it on main |
|---|---|---|---|---|---|---|
| one gap (as happened) | 3 | 3 | $60 | 1 | at its landing | at its landing |
| proof, then 2 hardening gaps | 3 (proof, hardened, its fix) | 3 (hardening review, hardened ×2) | $60 | 2 | about 08:00 plus the queue's wait | at the hardened gap's landing, about the same time |

What the example shows, without stretching it:

- **No saving here.** The same three reviews and three implementor sessions, moved later. With the flag off until
  `-hardened` lands, nothing is delivered earlier: the owner gets working verification at about the same time either
  way.
- **The flag alone was not "off".** Round 1's `queue.py` hooks (`reapplied()` and `taken_out()`) run with the lane
  off. Here, from the findings' descriptions, none of the six findings lay in that path: each was in code the lane
  reaches only when it is on, or in `queue.settle` handling the lane's own pending reverts. So this proof would have
  been safe on main with the flag off. Only a reading shows that, though, which is why the hook rule caps that code
  by counting lines rather than trusting the words "behind a flag" (lesson-8).
- **The proof's own list does not replace the review.** None of the six findings were on it. This is why every chain
  starts with a hardening review, and why the AI review is moved, not removed.
- **Where it would have paid.** Had the owner, seeing the lane on main, decided not to verify after merging, the proof
  would have cost one session ($15) against $60, and the time limit would have removed it. This proposal recommends
  the path for gaps like that: exploratory ones whose question is "is this worth building".

## Questions for the owner

1. Should the proof path be opt-in per gap (the planner or the owner writes `proof:`), only for exploratory work, as
   the record suggests? Or should it be offered for every gap, and measured?
2. Is 72 h, with one owner extension, the right limit before an unhardened proof is reverted?
