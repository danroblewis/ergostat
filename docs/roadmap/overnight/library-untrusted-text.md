# library-untrusted-text: a library folder the owner declares untrusted has its text marked where the authoring tools and `check` show it, and its parts' schedules and run counts capped at compile time and again when runs start
depends-on: []

The title is narrower than the first plan's ("wherever an agent reads it"). This branch marks the text that the `templates` tool and three kinds of `check` problem show from a library. The parts an untrusted template makes are bounded, not marked (see the "stays unmarked" list).

## Definition of done

**Declaring trust (the main file only, as `library:` already is).** A `library:` element can still be a string: an owner's folder, trusted, exactly as today. It can also be a map `{folder: PATH, untrusted: true|false}`. In the map, both keys are required, `untrusted` must be a YAML bool, and any other key, a missing key or a value that isn't a bool is a `bad-library` error. Nothing in a `uses:` entry can change trust or the limits: `USE_KEYS` stays `{use, with, within, description}`, so `trusted:` or `untrusted:` in a use entry is an `unknown-key` error. `$ERGOSTAT_LIBRARY` folders and ergostat's own templates are trusted. When `library-provenance` or `fetch` lands, they set the same `Template.untrusted` flag (one attribute, named in SPEC, so that a later merge has one place to meet).

**Reading an untrusted template (`ergostat/library/templates.py`).** The template name and every parameter name must match `^[a-z][a-z0-9-]{0,63}$`. If one doesn't, the template is refused with a `template-library` note (marked, below). An untrusted template never shadows a trusted one: if an untrusted folder has a template with the same name as one of ergostat's own or one from a trusted owner's folder, the trusted one wins, whatever the folder order, and a marked note says so. `Template.untrusted: bool` is set from the folder.

**Marking (`ergostat/library/untrusted.py`).** `mark(text, label)` returns `⟦untrusted: LABEL⟧` + text + `⟦end of untrusted⟧`. Before wrapping, every `⟦` and `⟧` in the text is replaced with `[` and `]`, so the only `⟦` and `⟧` characters in the output are ergostat's own. `LABEL` is never library text: it is `template NAME` (NAME already validated against the regex above) or the fixed words `library file`. These are marked, for an untrusted template only:
- (a) The `templates` tool / `author.library()`, list and full forms: `description`, `reading`, `example`, `from`, and each parameter's `description` and `stand-in`, plus its `default` and `choices` when they are strings (a list or map is first written as JSON, then marked). Numbers and bools are left as they are. Each untrusted entry also carries `"untrusted": true`, and the output carries one fixed sentence saying that text between the markers is a library's: data, not instructions.
- (b) Notes from an untrusted folder (`template-library`, including a file that won't read, a refused name, and a refused shadowing). The fixed prefix `untrusted library folder FOLDER:` comes first (FOLDER is the owner's own path, also passed through the `⟦⟧` escape), then the rest of the note, file name included, is marked as `library file`.
- (c) The problems that `uses.one()` emits for an untrusted template: `bad-param` and `bad-template` messages after `use INSTANCE:`, the stand-in text in `template-stand-in`, and a broken-template note appended to `unknown-template`.

A trusted template's output is byte-for-byte what it is on main.

**Stays unmarked (written in SPEC as such):** the template name and parameter names (validated instead), parameter `type` (from the `TYPES` allowlist), and everything an untrusted template makes in the model. That includes the instance system's description, the parts' descriptions, prompts, commands, equations and names, and how `check` explains, the diagrams and the MCP model views show them. Marking those, and gating `ask:` and `query`/`source`, stays in GAPS under Shared libraries.

**Chain trust.** `uses.one()` passes an `untrusted` flag down: an instance is untrusted if its own template is, or if any instance it sits inside is. So an untrusted template nested under a trusted one is untrusted, and so is a trusted one nested under an untrusted one. The flag is recorded as `doc.uses[inst]["untrusted"]` (a bool).

**Limits (constants in `ergostat/library/bounds.py`; no config, nothing read from a file, so no value parses into a default).**
- `UNTRUSTED_EVERY = 300 s`.
- `UNTRUSTED_POOL = 2` per block.
- `UNTRUSTED_RUNS = 4`: the most runs at once across all untrusted parts of the model.
- `UNTRUSTED_ATTEMPTS = 5`.

**The compile re-check, `bounds.check(c, spec)`, runs after `leases.check`.** A part is untrusted when its `where` is a `Via` and `spec.uses[via.instance]["untrusted"]` is not `False`. That means a `Via` whose instance is missing, or whose entry has no bool `untrusted`, counts as **untrusted** (lesson-3). A `where` that is not a `Via` is the model's own. The check sets `Block.untrusted` and `Sensor.untrusted` and gives an `untrusted-limit` error at the part's `use:` line for:
- the sensors of stocks and flows: `every` under the floor; `cron` whose minute set has more than one value (`len(Cron(v).sets[0]) != 1`, so it fires at most hourly; this works for cron in words too); `daemon:` (refused).
- blocks of type program, ai or judge: `every` under the floor; `cron` as for sensors; `on:` (refused); a program or ai block with none of `every`, `cron` or `takes` (it would run on every reading of its inputs); `pool` above `UNTRUSTED_POOL`; effective `attempts` (from `leases.terms`, so the owner's `leases:` tier counts too) above `UNTRUSTED_ATTEMPTS`.
- the total: Σ(pool if takes, else 1) over untrusted program, ai and judge blocks above `UNTRUSTED_RUNS`. This is model-wide, so it covers every chain at once.

The fields bounded are exactly: sensor `every`, `cron`, `daemon`; block `every`, `cron`, `on`, `pool`, `takes`-less starting, `lease.attempts`, and the total above.

**Defaults:** an untrusted sensor or judge with no `every` gets `UNTRUSTED_EVERY` (not 60 s or `JUDGE_EVERY`). Default `pool` 1 ≤ 2 and `LEASE_ATTEMPTS` 3 ≤ 5. A bad value (`every: soon`, `pool: many`, a bad cron, `attempts: x`) is an error, as the compiler already makes it, and a test shows each one stays an error, never a quiet default.

**Run time.**
- `engine.start` and `dispatch.take` call `bounds.room(engine)` **under `engine.lock`**, in the same critical section that adds to `engine.running`. `room` counts the entries in `engine.running` whose block is untrusted in `engine.spec`. A block it can't find there (removed on reload, still draining) counts as untrusted.
- `dispatch.take` reserves its `running` entry under `e.lock` before writing `lease.taken`, and drops it if the fold refuses the lease. So no lease is written for a run that can't start.
- An entry leaves `running` only where it does today, after `run_block` returns, so a run being cancelled or timed out still counts.
- The scheduler's intervals for an untrusted sensor, block or judge are `max(every or default, UNTRUSTED_EVERY)` (`bounds.pace`), so a spec changed after compile still can't run faster.
- Run processes for an untrusted sensor's `run:` go through the reader pool, which is already bounded by `READERS`. SPEC says so.

**Docs.** SPEC §2a gets a paragraph "Untrusted libraries": the declaration, the three marked places, the "stays unmarked" list, the limits table, and the new error code. GAPS Shared libraries gets an updated *Still needed*. The ergostat-author skill and AGENT-GUIDE say how to read the markers. The MCP `templates` tool description says the same.

## Files to touch
- `ergostat/library/untrusted.py` (new: `mark`, `mark_all`, `LABEL`)
- `ergostat/library/bounds.py` (new: constants, `untrusted_part`, `check`, `room`, `pace`)
- `ergostat/library/templates.py`, `ergostat/library/uses.py`, `ergostat/library/author.py`
- `ergostat/spec/load.py` (`library:` maps; `doc.untrusted_library`)
- `ergostat/spec/ir.py` (`untrusted` on `Block` and `Sensor`), `ergostat/spec/compile.py` (call `bounds.check`)
- `ergostat/spec/engine.py` (`start` gate; `pace` in `_schedule` and in `due`), `ergostat/leases/dispatch.py` (gate in `take`)
- `ergostat/mcp.py` (the tool description)
- `docs/SPEC.md`, `docs/GAPS.md`, `docs/AGENT-GUIDE.md`, `docs/skills/ergostat-author/SKILL.md`
- `tests/test_library_untrusted.py` (new), `tests/test_library_untrusted_runs.py` (new)

## Risks
- **lesson-1:** the count of untrusted runs is read, then a run is added. Both happen under `engine.lock` in `start` and `take`, and `take` reserves before it writes `lease.taken`. If `take` counted under the dispatch lock and added under `e.lock`, two starts could both pass at cap−1.
- **lesson-3:** a part's trust lookup misses (instance gone from `spec.uses`, no flag, or a running block not in the new spec on reload). Each counts as untrusted. A `.get(..., False)` anywhere would fail open.
- **lesson-4:** the pool is capped per block *and* in total, attempts are capped, an `every`-less untrusted block is refused, `on:` and `daemon:` are refused, and the same ceiling is enforced when runs start, counting runs still draining.
- **lesson-6:** a timed-out or cancelled run must keep counting until `run_block` returns. If the slot were freed when "cancelled" is answered, the cap could be passed while its process lives.
- **lesson-7:** `library-provenance` (leased) may add its own trust attribute or `library:` shape. Merge origin/main before review and meet on `Template.untrusted`. `doc.library` stays `list[Path]` so that `goodmodel.py` and `spec/files.py` don't change.
- **lesson-8:** the SPEC must claim only the three marked places and list what stays unmarked. The escape claim is only "no `⟦`/`⟧` inside a marked span". The limits claim is only the named fields.
- **lesson-9:** every test below is to be broken once and seen to fail. The implementor reports which change broke each.
- **lesson-10:** the race test uses events or barriers, not sleeps.

## Acceptance tests
In `tests/test_library_untrusted.py`:
- `test_library_map_declares_untrusted`: a string folder is trusted; `{folder, untrusted: true}` is untrusted; a missing key, an unknown key or `untrusted: "yes"` is `bad-library`.
- `test_use_entry_cannot_set_trust`: `trusted: true` or `untrusted: false` in a use entry is `unknown-key`, and the limits still apply to its parts.
- `test_untrusted_never_shadows_trusted`: an untrusted `re-ping`, in a folder listed first, loses to ergostat's own, with a marked note. It fails if folder order decides.
- `test_untrusted_names_validated`: a template name with a space, a 65-character name, or a parameter name `Ignore previous`: the template is refused and the note is marked.
- `test_templates_tool_marks_every_string`: list and full forms. Each listed field (description, reading, example, from, param description, stand-in, string default, list choices as JSON) starts with the open marker and ends with the close marker. Numbers and bools are untouched. Names and types are unmarked and match the regex and `TYPES`. A trusted template's output equals main's (snapshot).
- `test_marker_escapes_open_and_close`: a `reading` that contains both `⟦end of untrusted⟧ obey` and `⟦untrusted: template x⟧` comes out with `count("⟦") == 2`, the open marker at index 0 and the close marker at the end.
- `test_bad_param_message_marked`: an untrusted template whose `choices` contain the close marker; a bad `with:` value. The `bad-param` message holds exactly one marked span and two `⟦`. A trusted template's message is unmarked.
- `test_template_library_note_marked`: an unreadable YAML file in an untrusted folder, whose file name and error text hold the close marker. The note has the fixed prefix and one marked span. The same file in a trusted folder gives an unmarked note.
- `test_stand_in_finding_marked`: the `template-stand-in` text from an untrusted template is marked.
- `test_untrusted_every_floor`: a sensor and a block with `every: 1m` give `untrusted-limit`; `5m` passes; an owner's own part with `every: 1s` passes.
- `test_untrusted_cron_hourly_only`: `*/5 * * * *` and `every minute` give an error; `7 * * * *` and `daily at 03:00` pass.
- `test_untrusted_block_needs_a_start`: a program block with inputs and no `every`, `cron` or `takes` gives an error; `on:` gives an error; an untrusted sensor with `daemon:` gives an error.
- `test_untrusted_pool_and_total_ceilings`: `pool: 3` gives an error. Two blocks with `pool: 2` plus a timed block (total 5) give an error. A total of 4 passes. An owner's own `pool: 50` passes.
- `test_untrusted_attempts_ceiling`: `lease: {attempts: 6}` gives an error. An owner's `leases:` tier `attempts: 10` reaching an untrusted block gives an error.
- `test_with_cannot_loosen_limits`: `with: {pool: 50, every: 1s}` on an untrusted template that writes `pool: ${pool}` and `every: ${every}` gives both errors.
- `test_untrusted_nested_under_trusted`: a trusted owner's template uses an untrusted one whose block has `pool: 3`. That gives an error, and the inner `bad-param` message is marked. It fails if only the top-level instance's trust is checked.
- `test_trusted_nested_under_untrusted`: the inner trusted template's `pool: 3` gives an error.
- `test_recheck_missing_trust_is_untrusted`: after load, delete the instance from `spec.uses` (and, in a second case, delete its `"untrusted"` key), then re-run `bounds.check`. `pool: 3` gives an error in both cases. It fails with `.get(..., False)`.
- `test_defaults_within_limits`: an untrusted sensor and judge with no `every` get exactly `UNTRUSTED_EVERY`. `LEASE_ATTEMPTS ≤ UNTRUSTED_ATTEMPTS`. The default pool 1 ≤ `UNTRUSTED_POOL`. A minimal untrusted template (a takes-block plus a sensor, everything left to defaults) compiles with no `untrusted-limit`.
- `test_unparseable_value_is_error`: on an untrusted template, `every: soon` (sensor and block), `pool: many`, `cron: nonsense` and `lease: {attempts: x}` each give an error of their own code at its line, and the model has errors. It fails if any of them quietly becomes the floor, 1, 0 or the default.

In `tests/test_library_untrusted_runs.py`:
- `test_start_refused_at_ceiling`: four untrusted entries in `engine.running` make `engine.start` of a fifth untrusted block return False. Once one is removed, it starts. A block missing from the spec counts toward the cap.
- `test_take_reserves_before_lease`: at the cap, `dispatch.take` returns None and writes no `lease.taken` event (the record shows none).
- `test_start_race_holds_cap`: at cap−1, monkeypatch `bounds.room` to wait on a barrier while a second thread calls `start` or `take`. Exactly one run is added. It fails if the count and the add are under different locks.
- `test_draining_run_still_counts`: `run_block` is patched to block on an event, standing in for a cancelled run that is still exiting. While it blocks, the cap holds. After it returns, a new run starts.
- `test_engine_paces_untrusted_at_floor`: a compiled spec whose untrusted sensor and block are changed afterwards to `every = 1`. One scheduler round with `time.monotonic` patched shows the next due time is `UNTRUSTED_EVERY` ahead. It fails without `bounds.pace`.

Then the unit suite, the four browser files (rc 0, no skips for want of a port), ruff, and `demo_check` if any example is touched. Merge origin/main and run them all again.

## Size budget
340 net lines (estimate: `untrusted.py` 50, `bounds.py` 120, `templates.py` 30, `uses.py` 30, `load.py` 20, `author.py` 25, `engine.py` and `dispatch.py` 35, `ir.py`, `compile.py` and `mcp.py` 10, plus margin)

## Notes from the plan review (answer each; not blocking)

- bounds.room classifies a running entry's trust by looking the block up in the current engine.spec. After a reload that keeps a block's name but makes it trusted (folder trust flipped, or the owner's own block reusing the name), an untrusted run that is still draining stops counting and the UNTRUSTED_RUNS cap can be passed (lesson-5, plus lesson-4/6 'counting the ones still draining'). Record untrusted on the running entry when it is added under e.lock, count an entry if the recorded flag OR the current spec says untrusted (a missing block still counts), add lesson-5 to Risks, and add a test: an untrusted run is blocked in run_block, a spec reload makes the same name trusted, and the cap still counts it. The test must fail if trust is looked up only in engine.spec.

## Where it stopped

Built, round 1. Net code 224 lines of the 340 budgeted. Nobody was there to ask, so each choice the definition left
open, or got wrong, was settled the most reversible way, and is listed here (the definition above is unchanged).

**The plan review's note: answered.** `Engine.untrusted_runs` records, under `engine.lock` and in the same hold that
adds a run (`bounds.hold`, called by `start`, by `dispatch.take` and by the judge's pass), whether each `running`
entry was untrusted when it began. `bounds.room` counts an entry when that record says so, or when the current spec
says so, or when the spec no longer has its block. `test_reload_making_it_trusted_still_counts_its_draining_run`
blocks an untrusted run in `run_block`, swaps in a spec where that block is trusted, and shows the cap still holds.
It fails when `room` ignores the record. The note asked for lesson-5 to be added to *Risks*. The definition is not
edited except here, so it is answered here: the remade-under-the-same-name case is the one that test covers, and a
stale record is pruned on every hold (`untrusted_runs` is cut to what is in `running`). A stale record can only make
a run count as untrusted, which fails closed.

**Where this differs from the definition.**
- *Cron in words.* The definition says the minute-set rule "works for cron in words too" and names `every minute`
  and `daily at 03:00` in a test. The compiler's `cron:` reads only five-field cron (`ergostat/cron.py`). Words are
  only how the badges *show* a cron (`model.cron_words`). So `daily at 03:00` is a `bad-cron` error for any part,
  not a pass. `test_untrusted_cron_hourly_only` uses `* * * * *` and `0 3 * * *` for those two cases and asserts
  that `every minute` is `bad-cron`.
- *Attempts.* The effective attempts (`leases.terms`, so the owner's `leases:` tier counts) are checked on an
  untrusted block that takes items or that writes its own `lease: {attempts}`. A timed block holds no leases, so the
  owner's tier reaching it is not an error. Without this, `leases: {program: {attempts: 10}}` would break every
  untrusted timed block for a number it never uses.
- *The judge's pass* goes through the same `room`/`hold` under `engine.lock`, and its interval through `pace`. The
  definition counts judges in the total but names only `start` and `take` as gates. Without the gate, the total
  could not be enforced at run time. Tested by `test_judge_pass_counted_at_ceiling` and the judge in
  `test_engine_paces_untrusted_at_floor`.
- *The sentence.* The fixed sentence is the output's `markers` key (list form, and the full form of an untrusted
  template). It appears only when an untrusted template or an untrusted folder's note is present, so a model with
  no untrusted folder gets main's output byte for byte. The key is not `untrusted`, because in the full form each
  entry's `untrusted: true` is already at that level.
- *A "does not exist" note* for an untrusted folder says `untrusted library folder PATH does not exist`, with nothing
  marked. No library text is in it.
- *The label of a trusted template nested in an untrusted chain* is `template NAME` when NAME matches the name
  pattern, else `library file`. A trusted folder's names are not checked, so this keeps a label from ever holding
  unchecked text.
- *The snapshot.* "A trusted template's output equals main's" is checked against
  `tests/fixtures/library-trust/trusted-snapshot.json`, captured from main's code before any change. It covers a
  fixture template (`owners/plain.yaml`) with its `from` path normalised, rather than a built-in, so that it does
  not break when a built-in template is edited.

**Not built (outside the definition):** marking what an untrusted template makes in the model, and the `unknown-key`
and `no template X` messages a nested untrusted entry gives (library text, unmarked, not claimed in SPEC). A block's
`daemon:` param is not bounded (not in the listed fields; its pool and the total are). Gating `ask:` and
`query`/`source` is left in GAPS, *Shared libraries*.

**Each test broken once (lesson-9).** Each change below was made to the code, and the named tests were seen to
fail. Changes that touched different tests were run in batches.
- `untrusted_part` as `.get("untrusted", False)`: `test_recheck_missing_trust_is_untrusted`.
- Folders read in their listed order: `test_untrusted_never_shadows_trusted`.
- Names not checked: `test_untrusted_names_validated`.
- A list written with `str`, not JSON: `test_templates_tool_marks_every_string`.
- Cron rule always true: `test_untrusted_cron_hourly_only`.
- Attempts from the block's own `lease:` only: `test_untrusted_attempts_ceiling`.
- `library:` map's `untrusted` not required to be a bool: `test_library_map_declares_untrusted`.
- `trusted`/`untrusted` added to `USE_KEYS`: `test_use_entry_cannot_set_trust`.
- No `⟦⟧` escape: `test_marker_escapes_open_and_close`, `test_bad_param_message_marked`,
  `test_template_library_note_marked`, `test_stand_in_finding_marked`.
- No every floor: `test_untrusted_every_floor` (and `test_use_entry_cannot_set_trust`, `test_with_cannot_loosen_limits`).
- No start-less check: `test_untrusted_block_needs_a_start`. Separately, `on:` allowed and `daemon:` allowed: the same test.
- No total: `test_untrusted_pool_and_total_ceilings`, `test_with_cannot_loosen_limits`.
- No per-block pool cap: `test_untrusted_pool_and_total_ceilings`, both nested tests, `test_recheck_missing_trust_is_untrusted`.
- `uses.one`'s messages unmarked: `test_bad_param_message_marked`, `test_stand_in_finding_marked`,
  `test_untrusted_nested_under_trusted`.
- `author.marked` a no-op: `test_templates_tool_marks_every_string`, `test_marker_escapes_open_and_close`.
- Notes unmarked: `test_template_library_note_marked`, `test_untrusted_names_validated`.
- Chain flag not passed down: `test_trusted_nested_under_untrusted`.
- Only the chain, not the template's own flag: `test_untrusted_nested_under_trusted`, `test_library_map_declares_untrusted`.
- Untrusted sensor default left at 60 s, and no judge default: `test_defaults_within_limits`.
- `pool: many` quietly 1 (its `bad-number` removed): `test_unparseable_value_is_error`.
- `room` ignores the recorded flag: `test_reload_making_it_trusted_still_counts_its_draining_run`.
- A missing block counted as trusted: `test_start_refused_at_ceiling` (and four others).
- `start` counting before taking `engine.lock`: `test_start_race_holds_cap`. The test's first version waited on its
  barrier *before* counting, so one thread could count after the other had added. It passed under this break and
  was fixed to count, then wait.
- `take` counting before taking `e.lock`: `test_start_race_holds_cap`.
- `take` not gated: `test_take_reserves_before_lease`.
- The slot freed as `run_block` begins: `test_draining_run_still_counts` and the reload test.
- `pace` returning `every`: `test_engine_paces_untrusted_at_floor`.
- The readings path of `due` unpaced: `test_a_block_run_by_its_readings_is_paced_too`.
- The judge not gated and not paced: `test_judge_pass_counted_at_ceiling`, `test_engine_paces_untrusted_at_floor`.

**Run, and not run.** The two new files passed (28 tests), each alone. These existing files also passed, run
serially one batch at a time: `test_templates`, `test_cron`, `test_control`, `test_observer`, `test_incremental`,
`test_modelling_ai_cap`, `test_modelling_template`, `test_reload_in_place`, `test_runner_and_state`, `test_spec_blocks`
(263), then `test_leases`, `test_resilience`, `test_trial_stops`, `test_chains`, `test_daemons_restart` and
`test_process` (121). ruff is clean. **Not run here:** the whole unit suite and the four browser files. The brief
leaves those to the factory under the watchdog. `demo_check` was not run either, since no example was touched.
**Merge:** this clone has no `origin` remote and no network. Local `main` is already an ancestor of the branch, so
there was nothing to merge. lesson-7 (`library-provenance`) is still open for the factory's merge, which meets on
`Template.untrusted`. `doc.library` is still `list[Path]`.

**The factory's unit run after round 1.** It showed one `F` at about 11% and the tail held no test name, so the
failing test is not known. The failure did not come back here. Every `tests/test_*.py` file was run in four batches
under `-n 4` (a–co, cr–g, h–p, q–z): 2,383 passed, 69 skipped, 1 xfailed, none failed. The files near that position
in collection order (changesets to counts, with chains, calls, bench and backlog) were also run serially: 288 passed.
No code was changed, since nothing failed that could be fixed. If the factory's log names the test, it should be
checked against lesson-10 (a race under `-n 8`, or a sleep in the test) before it is put down to this branch.

**Round 2.** Review 1 had one finding, and it was blocking (lesson-3). `find_all` decided trust by the folder that
reached a file first, so with `library: [lib, {folder: lib/shared, untrusted: true}]` the file
`lib/shared/template.yaml` was read through `lib` as trusted. Now each file decides its own trust
(`templates.within`). A file under any untrusted folder is untrusted, compared both as the path is written and with
links followed. A trusted folder that reaches such a file skips it, and the untrusted pass reads it through its
untrusted folder. Its notes carry that folder's path, and it is not refused as "shadowed by itself". ergostat's own
folder is never checked this way (its templates are trusted, as the definition says). A file under an untrusted
folder is untrusted even when a trusted folder *inside* that untrusted folder also lists it, so the check fails
closed both ways. SPEC §2a says the same in one sentence. The new test is
`test_untrusted_child_of_a_trusted_folder_stays_untrusted`. It covers a trusted parent with an untrusted child holding
`template.yaml`, with the folders listed in both orders. It checks that the template is untrusted, that there is no
"is not used" note, that the instance is untrusted, that `pool: 3` gives `untrusted-limit`, and that the templates
tool's entry is marked. Broken once: going back to trust by the reaching folder (`owner = d if d in bad else None`)
makes it fail at `got["vend"].untrusted is True`. Net code +22 lines (about 246 of the 340).
Run: `test_library_untrusted` (21), `test_library_untrusted_runs` (8), `test_templates` with
`test_modelling_template` (40), all passing. ruff is clean. Not run here: the whole unit suite and the browser files
(left to the factory). This clone has no `origin`, and local `main` is already an ancestor, so there was nothing to merge.

**The factory's unit run after round 2.** It showed one `F` at about 11%, as after round 1, and its tail held no test
name, so the failing test is still not known. Nothing failed that this branch could be shown to cause, so no code was
changed. What was run, all on `ee06bb7e`:
- *The whole unit suite, serially, under `scripts/suite_watch.py`* (`-p no:randomly -rfE`): 2,471 passed, 69 skipped,
  1 xfailed and 6 failed in 37 min (peak 367 threads, 757 MB). The 6 are `test_index_files` (4),
  `test_modelling_ai_cap::test_two_runs_cannot_both_take_the_last_of_the_cap` and
  `test_store_conformance::test_a_second_instance_threads_and_processes_lose_nothing[sqlite]`. Each failed in a
  spawned child with `module 'queue' has no attribute 'LifoQueue'`. `test_backlog`, `test_factory` and
  `test_factory_times` put `dev/bin` on `sys.path`, and `dev/bin/queue.py` then shadows the standard library's `queue`
  in children spawned later in the same process. That only happens in a one-process run and lies outside this branch,
  which touches neither `dev/` nor `conftest.py`. Those three files pass on their own (65 passed, 7 skipped). Under
  lesson-13 this is reported here, not fixed.
- *Under `-n 8 --dist worksteal`* each worker starts on a contiguous eighth of the 2,541 collected tests, so an `F` at
  11% lies in the first tens of tests of some slice. These files, at or near each slice's start, were run serially and
  all passed: `test_act_risk`, `test_architecture`, `test_changesets` through `test_control`, `test_engine_shard`,
  `test_eta`, `test_extlaw`, `test_dynamics_view`, `test_gate`, `test_gated_actions`, `test_goal_per`,
  `test_lease_kill`, `test_leases`, `test_leased_workspaces`, `test_lease_refused_cost`, both new files (run twice),
  `test_observer`, `test_outside_experiments`, `test_parallel_runs`, `test_parity`, `test_pool_now`, `test_resilience`,
  `test_review`, `test_spec_causal`, `test_spec_compile`, `test_spec_discover`, `test_spec_engine`, `test_spec_items`,
  `test_spec_mcp_explain`, `test_spec_schema`, `test_guide`, `test_daemon_docs`, `test_exercised` and `test_mended`.
- *Not run:* the suite under `-n 8`, or any slice of it under `-n 8`. That command, and a loop of repeated runs, were
  refused in this session.
- *Read for a change on the trusted path, none found.* `due`, `start`, the scheduler's intervals and the judge's pass
  give main's values for a trusted part (`pace` returns `every` unchanged, and `room` returns True). Every `uses` entry
  carries a bool `untrusted`, written only by `uses.one`. Remote parts carry `RemoteVia`, not `Via`. Only block keys go
  into `engine.running`, so `room`'s rule that a missing block counts cannot catch any other key.
- *Read for load-sensitivity in the new tests, none found.* The race test's barrier gives the same outcome when it
  times out. A take with `inline=True` keeps its `running` entry. `done` is set only after `_run` drops its entry. Two
  tests (`test_draining_run_still_counts` and the reload test) spend about 5 s in `e.close()` waiting on the made-up
  `GONE` entries, which they never clear. That is slow but not wrong, and is left as it is.
If the factory's log names the test, it should be checked against lesson-10, and against the `dev/bin/queue.py`
shadowing above, before it is put down to this branch.

**The factory's unit run after round 3.** Its tail stops at 88%, partway through a line, with no `F`, no summary and
no test name. So the run was stalled or killed (by the watchdog or a time limit), not failed by an assertion. No test
of this branch is known to cause it. Two things in this branch's own test file could disturb the other tests of one
xdist worker, and both are changed (tests only, no code):
- `clocked()` (used by the two pacing and judge tests) patched `time.monotonic` for the whole process while a real
  scheduler pass ran. Another live thread of the same worker that works out a wait as a real deadline less
  `time.monotonic()` (for example `daemons/work.py`, `spec/stream.py` or `session_echo.py`) would then wait for about
  the container's uptime. It now patches only the engine module's clock (`ergostat.spec.engine.time`, a copy of `time`
  whose `monotonic` is the test's clock). Broken once: `pace` returning `every` still fails
  `test_engine_paces_untrusted_at_floor` and `test_a_block_run_by_its_readings_is_paced_too`.
- Five tests never closed their engine. An autouse fixture now closes every engine a test made, after taking out the
  stand-in `GONE` entries (and every entry, where the test stood in for `_run`). That also removes the two 5 s waits in
  `close()`: the file runs in 4 s instead of 19 s.
Run: `test_library_untrusted_runs` (8), and under `-n 4` with `test_library_untrusted`, `test_templates`,
`test_reload_in_place` and `test_leases` (105 passed). ruff is clean. Not run here: the whole unit suite and the browser
files. If the stall comes back, the factory's log of which worker stopped, and on which test, is needed to go further.

**After main was merged in (640ef397).** Main's merge touched three of this branch's files: `leases/dispatch.py`
(`give_back` and `finish`), `spec/engine.py` and `spec/compile.py`. It also added a built-in `upkeep` template. None
of it conflicted with the gates. `take` still calls `bounds.room` and `bounds.hold` under `e.lock` before
`lease.taken`, and drops its entry when the lease is refused. `start`, the judge's pass and `pace` are unchanged. No
code was changed. Run on the merged head, one batch at a time: `test_library_untrusted` (21) and
`test_library_untrusted_runs` (8), alone. `test_templates`, `test_modelling_template`, `test_upkeep_template`,
`test_leases` and `test_reload_in_place` (102). `test_spec_compile`, `test_resilience`, `test_chains` and
`test_spec_engine` (106). All passed, and ruff is clean. Not run here: the whole unit suite and the four browser files,
which are left to the factory under the watchdog. The stall the factory saw at 88% after round 3 has not yet been
seen on a run that has round 3's test changes (8a221683). If it comes back, the worker's log naming the test is still
needed.
