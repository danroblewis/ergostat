# Overnight run, 2026-11-19

The owner asked for the known gaps (`docs/GAPS.md`) to be closed overnight and into the day, as parallel as
possible, without check-ins. Check-ins are replaced by gates written down in advance. The run ends at
**12:00 on 2026-11-19**, or earlier if the queue empties, with one report.

## Gates (instead of check-ins)

1. **Done is defined first.** Each branch's first commit is `docs/roadmap/overnight/<branch>.md`: the gap,
   a one-paragraph definition of done, the acceptance tests by name, and its size budget. The gate checks
   that the file was not changed after the first commit, except to add a "Where it stopped" section.
2. **A branch merges only when:**
   - all four suites pass with rc 0 (unit; the four Playwright files; ruff; `demo_check` on the examples it
     touches);
   - no page test was skipped for want of a port;
   - its acceptance tests exist and pass;
   - it is within its **size budget:** net lines of code outside `tests/` and `docs/`, 600 by default. An
     overrun needs a written reason in the definition file;
   - an independent reviewer (Opus, deliberately disagreeable) has found nothing blocking. The reviewer judges
     the branch against its definition of done, the gap entry, SPEC, and the owner's recorded rules (no new
     pages or panels; the disciplines' own terms; main always installable).
3. **Partial work never reaches main.** It stays on its branch, and the definition file and GAPS say what is
   done, what is left and why it stopped.
4. **A merge queue.** Branches merge one at a time: rebased onto main, all suites run, merged, pushed. Work
   runs in parallel; landing is serial.
5. **Kill rules.** A branch that fails its gates twice, or overruns 4 hours, stops and writes up where it
   stopped.
6. **No questions overnight.** A decision only the owner can make is either left alone or taken with the
   most reversible option, and listed under *Decisions taken* below.

## Limits

- About 6 agents at once, Opus.
- AI inside ergostat runs on haiku. The redesign and architecture reviews may use a larger model, with
  their costs recorded.
- Every load or soak run is watchdogged: kill past 1,500 threads or 6 GB.
- Tests take free ports from the system.
- Servers started by hand use 8791–8797. 8790 is the owner's page; 8798 is the ergostat-dev instance.

## Queue (in dependency order; see the dependency notes in GAPS)

| Wave | Branch | Gap | Depends on |
|---|---|---|---|
| running | `closedloop` | closed-loop simulation, what-if, risk | — |
| running | `layout` | layout rules, detectors, valve as point | — |
| running | `upkeep` | upkeep survey, prototype, fault injection | reloadfix, indexfix (merged) |
| A | `selfimprove` → `redesign` | finish verification, rebase, land both | — |
| A | `triggers` | triggers on an event type → causes for scheduled runs → built-in join | relations (merged) |
| A | `leasekill` | kill a run whose lease expired → warm workers | — |
| A | `ergostat-dev` | an observe-only ergostat instance watching this run (outside the repo) | — |
| B | `observer` | observer staleness and estimated stocks | — |
| B | `architecture` | system architecture review: computed measures, per-system redesign, daily larger model | redesign |
| B | `extremes` | extreme-conditions tests; proposals that state their predicted behaviour | closedloop |
| B | `resilience` | from upkeep's fault injection: the CLI reads the record with the last good model while the YAML is broken; an outer watcher that restarts a dead engine (`--service`); the watchdog finds the cause and backs off; alarms shown; caps on unbounded files | reloadfix, indexfix |
| B | `smallgaps` | per-kind goals, light-theme contrast, relations leftovers, external event logs | — |

**Not tonight:**
- the IR and Rust runtime (waits on the owner's 12 questions);
- finding structure from residuals (research; after `observer`);
- shared libraries (design choices);
- identifying existing controllers (after `closedloop`);
- operating modes (after `upkeep` and `closedloop`);
- remodelling the-job (last; a test for redesign).

## Progress log

- 00:45 Merged reloadfix, indexfix, gapsfix and reports. Tests now take ports from the system. Wave A started.

- 01:10 closedloop finished; gate review: merge after fixes (state not restored for five built-ins, selective validation write-up, invalid risk runs dropped, no definition file; ~300 lines of bloat). Sent back.
- 01:30 upkeep finished (exploration; proposal in docs/proposals/upkeep.md). Its fault injection found five real problems, queued as `resilience`, first in wave B.
- 02:05 Main green (1338 unit, browser rc 0 with no skips, five demos ok): pushed reloadfix, indexfix, gapsfix, reports, the port change. leasekill finished (281 net lines, 2.2x latency with warm processes), in review. layoutopt started (an experiment the owner asked for: pure optimisation layouts). GAPS: superseded proposals, and the judge on slow models (owner).
- 02:40 Reviews: leasekill, triggers and resilience all merge-after-fixes, each with real bugs (warm workers' per-item state, cost and kills; an event trigger bypassing `mode: advise`, and blocks triggering each other forever; the CLI fallback running commands in the copy, the engine staying down after a reboot, `compact --projects` on unmounted drives). Sent back. smallgaps started.
- 03:05 leasekill's warm path failed its second review (children's CPU uncharged, env leaks, loose done detection, misattributed stops): split. The lease kill lands alone; warm processes parked on `warm` with where it stopped. smallgaps done (158 lines), in review.
- 03:20 layoutopt (experiment) finished: today's pipeline wins overall; WebCola scores lower only by spreading out; annealing moves 69% of parts on one edit. Parked as reference; next idea: rule cost as a test referee, Cola's constraints as one compaction step. It found 8 page-test failures on `layout` itself. triggers fixed, in re-review.
- 03:30 triggers' second review failed (loops of 5+ blocks run forever; a full table scan per hop stalls the engine): split. Scheduled causes and the join land as `causes-join`; `on:` triggers parked.
- 03:35 smallgaps review: merge after fixes. The light-theme colours pass 3:1 but blur together (gold and olive, orange and the warning colour): the colour commit is dropped and the gap reopened for a design pass.
- 03:50 resilience's re-review failed narrowly (the fallback never keeps AI models with prompt files; the alarm pool can leak threads; `#!` launcher parsing). One final 45-minute round allowed (see Decisions taken); split if it fails.
- 04:00 leasekill-only merged locally (66 lines), suites running. warm parked. selfimprove and redesign rebased and green (+2,662 and +1,921 lines, both before the budget); refinement reduced findings in no example, redesign fixed the planted ones. In review.
- 04:20 resilience's final round fixed its three items but the fallback now mixes the kept YAML with include files on disk (a model that never existed): split. `resilience-core` (watcher, watchdog, alarms, caps, service) lands; the CLI fallback is parked.
- 04:40 selfimprove + redesign review: seven blocking (a redesign could rewrite the owner's accept policy; a setpoint change passed as a rename; rule-tier rewiring without `rewires`; renames editing program files; a stuck redesign blocking the queue; redesigns run inside the web server, uncosted; installed builds lose checklists). Split: `modelling-core` (craft notes, use: modelling, renames with history, descriptions, redesign) lands after fixes; the rule tier's equations, event renames and chain copies are parked; redesign runs only when asked.

- 04:55 causes-join merged and pushed (b53a933). smallgaps conflicted with it: rebasing. resilience-core's merge hit the flaky stop_still_kills test (fails on main 1 in 13; its run lasts 2 s against the reload's 1.5 s settle): fixing the test. observer review: merge after fixes; made opt-in (it slowed every model's pass 20-50x and raised false model-disagrees on item counts). closedloop's fixes in (1,162 net lines, down from 1,438), suites running.

## Decisions taken (for the owner to confirm)

- `ergostat run --service` keeps printing the unit by default, as recorded in cli-rounds.md; installing needs `--service --install` (the resilience branch had made install the default).
- The light-theme contrast change is dropped, not merged: meeting 3:1 for the faded repeats forced every hue to one lightness. Reopened for a design pass (an outline or dash for the faded round, or alternating lightness).
- The kill rule (two failed gates) was bent once for `resilience`: one final 45-minute round for three small, exact fixes, because its CLI fallback is what the owner's work laptop needs most. If it fails, it is split.
- Redesign runs only when the owner asks (`when: ask` default); the automatic triggers are parked until a redesign on a large model succeeds (the-job's never compiled).
