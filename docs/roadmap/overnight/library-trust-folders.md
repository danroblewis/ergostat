# library-trust-folders: a `library:` folder can be marked untrusted; its templates never shadow trusted ones, and a use whose chain holds one may make only parts on an allowlist, or the whole chain is refused
depends-on: []

## Definition of done

On main today every `library:` folder and `$ERGOSTAT_LIBRARY` counts as the owner's (`ergostat/library/templates.py`, `find_all`). No trust gate exists. When this branch is done:

1. **Folder form.** `library:` (main file only, as now) accepts a path (the owner's, trusted, as today) or a map `{folder: PATH}`. The map form is **untrusted** unless it says `trust: owner`. A map with any other key, a missing `folder`, or a `trust:` value other than `owner`/`untrusted` is an error (`bad-library`) at that line, and its templates are not loaded at all (fail closed, never trusted). `$ERGOSTAT_LIBRARY` stays the owner's. `Template` gains `trust`: `ergostat`, `owner` or `untrusted`. `Template.summary()` and the MCP `library` tool (`author.library`) show it.
   - If origin/main already has another way to mark a library untrusted by the time this merges (library-untrusted-text is being built in parallel), the branch uses that one and drops the map form. Every test below still stands, written against that form.
2. **No shadowing.** An untrusted template whose name is a built-in's or a trusted template's is never used, whatever order the folders are listed in. The trusted one is used, and a `template-library` finding says which was skipped. Between untrusted folders the first wins, as now.
3. **The allowlist.** A new `ergostat/library/trust.py` classifies every section a template may write (`templates.BODY`) and every section in `load.SECTIONS` as allowed or refused for a held chain:
   - **Allowed sections:** systems, items, parameters, auxiliaries, stocks, flows, goals, blocks, uses.
   - **Refused sections:** everything else, including agents, workspaces, actions, sources, claims, contexts, leases, daemons, loops and variables.

   For each allowed section it lists the keys allowed at each path. Any key, section or block type not listed is refused, so a key that compile gains later fails closed. Each listed key carries a one-line reason in trust.py. At least these are refused:
   - every block type except onoff, compare, proportional, limit, delay, schedule, lookup, select, expr, timer, counter and alarm (so program, ai, person, external and judge are refused, as is a block with no type);
   - block `on-stale`;
   - sensor `run`, `query`, `daemon`, `push`, `parse`, `every`, `cron` and `timeout`;
   - item `lease`;
   - goal `owner` and `on-stale`;
   - `inferred` and `formerly` anywhere, because a library may not claim ergostat inferred a part (invariant 11).
4. **Held chains.** A use is **held** if its template, or any template it uses at any depth, is untrusted. Everything made from the first untrusted template downward is checked against the allowlist, including trusted and built-in templates nested under it. Expansion of the whole chain completes before anything is put (`uses.one` is restructured). If any part fails, **the whole chain from the owner's `use:` line is refused**:
   - one error, code `library-untrusted`, at the depth-0 `use:` line in the owner's file;
   - the error names the template, its folder and the first refused path (e.g. `blocks.x-fetch.run`);
   - no part of the chain is in the spec at any depth: no system, no section entry, no `doc.uses` entry for any instance in it.
5. **The refusal never launders.** The message never quotes the refused value and never suggests `with:` or `trust: owner`. It says that only the owner can mark a folder trusted, after reading it.
6. **Docs:**
   - SPEC §2a covers the map form, trust, no-shadow, what a held chain may make, and the `library-untrusted` entry in the problems list.
   - docs/SECURITY.md gets a section, *Libraries you did not write*. It lists what an untrusted folder may make. It says what this does **not** stop: its descriptions, `example:` and `reading:` reaching agents (gap library-untrusted-text); the owner's `trust: owner` or a path entry being trusted wholesale; and an agent that can write the main file can mark a folder trusted.
   - AGENT-GUIDE says an agent never writes `trust: owner` or turns a map entry into a path; it asks the owner.
   - GAPS "Shared libraries" is updated.
7. **House rules:** the unit suite and the four browser files pass with rc 0 (no page test skipped for want of a port), ruff is clean, and origin/main is merged in with both suites run again.

## Files to touch
- `ergostat/library/trust.py` (new)
- `ergostat/library/templates.py`
- `ergostat/library/uses.py`
- `ergostat/library/author.py`
- `ergostat/spec/load.py`
- `docs/SPEC.md`
- `docs/SECURITY.md`
- `docs/AGENT-GUIDE.md`
- `docs/GAPS.md`
- `tests/test_library_trust.py` (new)

## Risks
- **lesson-8:** "an untrusted library cannot make anything that runs" holds only if the list is an allowlist that covers every key. A denylist of `run`/`agents` would miss `query`, `daemon`, `judge`, `lease`, a new section or a new key. Guarded by allowlist matching, by `test_every_compile_key_classified`, and by the parametrized refusal test. SECURITY must not claim more than what is listed, and must name what is not stopped.
- **lesson-3:** each of these must count as untrusted or refused, never trusted:
  - a malformed map entry;
  - an unknown `trust:` value;
  - a template whose trust can't be determined;
  - a block with no `type`;
  - a value of unexpected shape under an allowed key.

  Covered by `test_library_map_entry_bad_key_or_trust_is_an_error` and `test_untrusted_unknown_key_refused`.
- **lesson-5:** the template cache on the document (`doc._templates`) or the authoring tools could keep a folder's old trust after the main file changes. Covered by `test_trust_follows_a_reload`.
- **lesson-9:** a refusal test that only checks that some error exists passes when the refusal is for some other reason, such as compile's own unknown-key error. Tests assert the code `library-untrusted`, its line, and that nothing from the chain is in the spec. Each new test is broken once and seen to fail (allowlist made to accept everything, no-shadow removed, the put moved back before the check), and the report says so.
- **lesson-7:** library-untrusted-text is being built at the same time and may add its own untrusted marker. Merge origin/main, keep one marker (point 1), and run both suites again.
- **Not applicable here:** lessons 1, 2, 4, 6 and 11. Nothing new is concurrent, timed, counted or destructive; folders are only read.

## Acceptance tests
All of these are in `tests/test_library_trust.py`.
- `test_library_map_entry_is_untrusted_by_default`: `{folder: P}` gives untrusted templates, and `{folder: P, trust: owner}` gives owner ones. A path entry and `$ERGOSTAT_LIBRARY` give owner templates. `author.library()` shows each one's trust.
- `test_library_map_entry_bad_key_or_trust_is_an_error`: `{folder: P, trust: yes}`, `{path: P}` and `{folder: P, extra: 1}` each give `bad-library` at that line, and the folder's templates are not loaded.
- `test_untrusted_never_shadows_builtin_or_owner`: an untrusted `collect` and an untrusted copy of an owner template are each listed before and after the trusted one. The trusted one is used every time, and the finding names the skipped file.
- `test_untrusted_structure_only_template_expands`: an untrusted template that makes items, stocks, flows, goals, an onoff block and an items-counting sensor (no `every`) expands and compiles with no errors.
- `test_untrusted_refused_at_use_line[...]`: parametrized over a program block's `run`, an ai block, a person block's `ask`, an external block, a judge block, a block with no type, and sensor `run`, `query`, `daemon`, `every` and `parse`. It also covers the agents, workspaces and actions sections, `parameters.x.inferred`, item `lease` and goal `owner`. For each case: exactly one `library-untrusted` error at the owner's `use:` line, and no part in the spec.
- `test_untrusted_unknown_key_refused`: a key no allowlist lists (e.g. `blocks.x.zzz` on an onoff block) is refused with `library-untrusted`, not only compile's unknown-key error.
- `test_untrusted_wrapping_builtin_with_run_refused`: an untrusted template that uses built-in `collect` is refused, because collect writes sensor `run` and `every`.
- `test_nested_chain_refused_whole`: the owner uses trusted T1, T1 uses untrusted L, and L uses built-in `collect`. There is one error at the owner's line. No system, item kind, stock, flow or block from T1, L or collect is in the spec, and `doc.uses` has none of the chain's instances.
- `test_refusal_text_suggests_no_copy`: the message contains neither the refused value, `with:` nor `trust: owner`.
- `test_every_compile_key_classified`:
  - (a) `set(templates.BODY) | set(load.SECTIONS)` equals trust's allowed sections plus its refused sections, and the two are disjoint.
  - (b) every key in each `*_KEYS` constant and `TYPE_KEYS` in `ergostat/spec/compile.py`, `ergostat/actions/compile.py`, `ergostat/workspaces/compile.py` and `ergostat/leases/compile.py`, and every literal set passed to `self.keys(` in `spec/compile.py` (an AST scan), is classified allowed or refused for its section.
  - (c) the checker is a function in the test. It is called once more with `load.SECTIONS` plus a made-up section and with `SENSOR_KEYS` plus a made-up key, and must report both, so the test is shown to fail when compile gains either.
- `test_trust_follows_a_reload`: the main file's entry changes from path form to map form, the model is reloaded, and a use that compiled before is now refused.
- The existing tests in `tests/test_templates.py` and `tests/test_modelling_template.py` pass unchanged.

## Size budget
330 net lines outside tests and docs: trust.py about 150 (mostly the tables), templates.py about 45, uses.py about 80 (expanding the chain first, then the gate), load.py about 25, author.py about 10.

## Notes from the plan review (answer each)

- Sensors are not in the allowed-sections list (systems, items, parameters, auxiliaries, stocks, flows, goals, blocks, uses), yet point 3 refuses specific sensor keys and test_untrusted_structure_only_template_expands needs a sensor. If sensors is a top-level BODY or load.SECTIONS section, 'everything else is refused' contradicts that test. State the path where sensors live, and list every allowed sensor key at that path in trust.py.
- Block keys must be allowlisted per block type, not as one union across all types. Otherwise a key that is safe on one type passes on another. Also check that the allowed types alarm, schedule and timer have no keys that notify, call out or trigger actions. Each of their allowed keys needs its one-line reason saying it doesn't.
- Lesson-3 names 'a template whose trust can't be determined' and 'a value of unexpected shape under an allowed key', but no test covers either. Add a test for each: a Template with trust unset or unknown is treated as untrusted and the chain is held; a mapping or list under an allowed scalar key (e.g. a nested {run: ...}) is refused with library-untrusted.
- The check runs on the expanded parts, after `with:` substitution. Say this in trust.py, and add one parametrized case where the refused key only appears after substitution.
- Point 1's fallback (use library-untrusted-text's marker instead) would void test_library_map_entry_bad_key_or_trust_is_an_error as written. If the fallback is taken, the report must say what that test became and show that the other marker's malformed values still fail closed.
- test_untrusted_never_shadows_builtin_or_owner should also cover a trusted template that uses a name an untrusted folder also defines. The trusted one must resolve, and the chain must not be held.
- For each break-once in lesson-9 (allowlist accepts everything, no-shadow removed, put moved before the check), the report names which tests failed.
- SECURITY's list of what an untrusted folder may make must be generated from, or checked against, trust.py's tables, e.g. by a test comparing the doc list with the allowed sections. Otherwise the doc can drift wider than the code (lesson-8).

## Where it stopped

Built, round 1: points 1–6, and point 7 in part (below). 266 net lines outside tests and docs (budget 330):
trust.py 194, uses.py 47, templates.py 16, load.py 8, author.py 1.

**Not run here, left to the factory:** the whole unit suite and the four browser files (the brief says the factory
runs them under the watchdog). The merge of origin/main was not done: this clone has no `origin` remote and no
network, and local `main` has nothing past the branch's base. Run here: `tests/test_library_trust.py` (40 passed),
`tests/test_templates.py` and `tests/test_modelling_template.py` unchanged (40 passed), ruff clean.

**Point 1's fallback not taken:** main has no other untrusted marker (library-untrusted-text is not merged), so the
map form stands and `test_library_map_entry_bad_key_or_trust_is_an_error` is as written (six bad entries).

**Decisions taken alone (the most reversible; each narrows what an untrusted folder may make):**
- Sensor `builtin`, `manual` and `averages` are refused too, not only the eight listed. `builtin` starts ergostat's
  own measure as a process on a timer, `manual` asks a person, and `averages` only means something on those. Allowing
  any of them later is one line in `trust.SENSOR`.
- A folder listed both as a path and as an untrusted `{folder:}` counts as untrusted (fail closed). So does an
  `$ERGOSTAT_LIBRARY` folder that is also listed untrusted.
- When a chain is refused, its own nested errors and findings are dropped with it. The one `library-untrusted` error
  is all that is reported.

**The plan review's notes, answered:**
- Sensors live inside parts, not as a section: `stocks|flows|auxiliaries.X.sensor` and `.sensors.NAME`. trust.py's
  `SENSOR` lists every key allowed there (items, state, entering, leaving, where, over, measure, sum, changes, unit,
  description), and the refused ones by name.
- Block keys are allowlisted per type (`trust.BLOCK_TYPES`, joined only with the common `BLOCK`). The alarm, schedule
  and timer keys each carry a reason saying they output a number and start or send nothing. What a raised alarm does
  (shown on the page, counted as an intervention) is listed under SECURITY's "does not stop".
- Trust unknown: `Template.trust` defaults to `untrusted`, and `templates.trusted` accepts only `ergostat` and
  `owner`. Tested by `test_a_template_whose_trust_is_unknown_is_held`. Shape: the `map-under-a-value` and
  `list-under-a-value` cases.
- After substitution: said in trust.py's docstring, and tested by the `after-substitution` case (a `type: map`
  parameter's default `{run: ...}` put whole under `sensor:`).
- Shadowing by a trusted chain: in `test_untrusted_never_shadows_builtin_or_owner`, the owner's `wraps` uses
  `collect` while the untrusted folder has a `collect` of its own. Ergostat's resolves, and nothing is held.
- SECURITY's lists are checked against trust.py by `test_security_lists_what_trust_allows` (sections, block types,
  sensor keys).
- Break-once (lesson-9). Each break was seen to fail, then restored:
  - allowlist accepts everything (`refused` returns None): 27 failed. These were every
    `test_untrusted_refused_at_use_line` case (21), `test_untrusted_unknown_key_refused`,
    `test_untrusted_wrapping_builtin_with_run_refused`, `test_nested_chain_refused_whole`,
    `test_a_template_whose_trust_is_unknown_is_held`, `test_refusal_text_suggests_no_copy` and
    `test_trust_follows_a_reload`;
  - no-shadow removed: both `test_untrusted_never_shadows_builtin_or_owner` cases failed;
  - the put moved back before the check: the same 27 failed as for the first break.

### Round 2

The review's two findings, answered:
- **`out:` commands the owner's machine blocks (lesson-8).** Taken the narrower way: a held chain's block `out:` may
  name only parts the chain made itself (`trust._out`, `trust.OUT_TO`; the set of parts is everything checked from the
  first untrusted template down, so a trusted parent's blocks don't count either). An `out:` to the owner's program
  block, to the owner's goal, to a part that exists nowhere, or one that is not a reference is `library-untrusted` at
  the `use:` line (`test_untrusted_out_to_a_part_it_did_not_make_refused`, 5 cases, which also asserts the owner's
  `deploy` block has no commanders). `test_untrusted_out_to_its_own_part_compiles` shows the chain's own `out:` to its
  own block and goal still compiles. The false reason in trust.py is replaced. SECURITY now says this, and its
  "does not stop" item is narrowed to what is true: the chain's parts may still *name* the owner's (`in:`, `goal:`,
  a flow's `from:`/`to:`, `driven-by`, `within:`), and an owner's machine block that reads a library block is
  commanded by it, by the owner's wiring. GAPS and SPEC §2a say the same. Break-once: with `_out` removed from
  `refused`, all 5 `out:` cases failed, and the other 41 passed. Restored, all 46 pass.
- **origin/main not merged (lesson-7).** The merge is the branch's commit 6a5ee51d. It merges `main` at 7b39bc94,
  which holds the 7 pipeline-manager/plan-review commits. This clone still has no `origin` remote, so I could not
  check that 7b39bc94 is the review's 3adf48a. If origin/main has moved past it, the factory merges again.

Run here, after the merge: `tests/test_library_trust.py`, `tests/test_templates.py` and
`tests/test_modelling_template.py` (86 passed), and ruff is clean. **Not run here:** the whole unit suite and the four
browser files. The brief leaves them to the factory, under the watchdog, so their result after the merge is not
known yet.
Size: 286 net lines outside tests and docs (budget 330): trust.py 213, uses.py 48, templates.py 16, load.py 8,
author.py 1.

### The factory's unit run after round 2

1 failed, 1988 passed, 69 skipped: `tests/test_warm.py::test_the_owners_stop_is_said_only_on_the_run_it_stopped`
(its 5 s wait for the stopped run's warm process to be replaced ran out). Not fixed here (lesson-13): this branch
changes nothing in `ergostat/daemons/`, `ergostat/leases/`, the engine or `tests/test_warm.py` (`git diff main...HEAD
--stat` on them is empty). Its code is only `ergostat/library/` and `ergostat/spec/load.py`, and no warm test model
has a `library:` or `uses:` line. Run alone here, `tests/test_warm.py` passes, 21 of 21. It failed under `-n 8` with
the whole suite running (287 threads), so it looks like a load-dependent timing in how the warm daemon replaces a
cancelled run's process (lesson-10). That belongs in its own gap: either replacing the process really is slow under
load, or the test's wait is fixed. The suite should be run again. If it fails on main too, it is not this branch's.

### The factory's second unit run after round 2

The tail it gave stops at 77% with no `F`, no error and no summary line. The run was cut off (killed, or timed out
before pytest printed anything), and the tail names no failing test. With no failure to fix, no code was changed.
The whole suite could not be run from this worktree (not permitted here). Instead, every test file that touches
templates, `uses:`, `library:` or the authoring tools was run alone, and each passed:
- `test_library_trust` (46);
- `test_templates` and `test_modelling_template` (40);
- `test_modelling_core` (24) and `test_cli_fallback` (17);
- `test_interventions` (10), `test_redesign` (19), `test_redesign_bench` (6) and `test_self_improve` (10);
- `test_repair2` (32 skipped: they need the sandbox);
- `test_warm` (21; this was the first run's one failure).

Ruff is clean. No code outside this branch calls `find_all` or `read` with the old arguments. `templates.read` is the
only place a `Template` is made, so no caller gets the `untrusted` default by accident.

**Left:** run the unit suite and the four browser files again under the watchdog, keeping the full output, so that
any failure can be named.

### Round 3

Both of the earlier review's blocking findings were answered in round 2 (above). This round, no code changed:
- **The merge (lesson-7).** The factory merged main at d7ae7a01 into the branch (5372045e). `main` is now an ancestor
  of HEAD, and `git diff main...HEAD` is only this gap's 11 files (trust.py, templates.py, uses.py, author.py,
  load.py, the four docs, the definition and `tests/test_library_trust.py`), so the branch carries nothing else
  onto main. Main still has no other untrusted marker for libraries (nothing under `ergostat/` names one), so
  point 1's map form stands. This clone has no `origin` remote, so I could not check that d7ae7a01 is origin/main's head.
- **Run here, after the merge:** `tests/test_library_trust.py` (46 passed), `tests/test_templates.py` and
  `tests/test_modelling_template.py` (40 passed, unchanged), `tests/test_modelling_core.py` (24) and
  `tests/test_cli_fallback.py` (17). Ruff is clean. Running more files was not permitted in this worktree.
- **Not run here:** the whole unit suite and the four browser files. The brief leaves them to the factory, under the
  watchdog. The second run after round 2 was cut off at 77% and named no failure. The first run's one failure was
  `test_warm`, which is outside this gap (see above).

**Left:** the unit suite and the four browser files, run under the watchdog with the full output kept.

### The factory's unit run after round 3

The tail it gave holds only start-up (`bringing up nodes...` twice) and 36 dots: no `F`, no `E`, no traceback and no
summary line. The run was cut off a few seconds in, and it names no failing test, so no code was changed (nothing
to fix, and this brief says to fix the code, not the tests' bounds). In this worktree I could not run the whole
suite or start it under `scripts/suite_watch.py` (the call was refused). What I ran here:
`tests/test_library_trust.py`, `tests/test_templates.py` and `tests/test_modelling_template.py` (86 passed in 110 s).
`tests/test_library_trust.py` alone took 6.5 s, and its slowest test 0.49 s, so none of this gap's tests can hold a
worker long enough to stall the run. The 110 s is the existing template tests' trial runs, which this branch does not
change. Nothing in the diff can loop: the chain's depth is still capped by `expand.MAX_DEPTH`, and `plan` recurses
exactly where `one` used to. Ruff is clean.

**Left:** the same as before. Run the unit suite and the four browser files again under the watchdog, keep the
whole output, and name any failure. Three runs have now ended with no named failure from this branch (one
`test_warm` timing failure outside the gap, then two cut-offs). If the next run is also cut off, look at the slot or
the watchdog's kill (its JSON line says whether it killed the run and why), not at the code.

### The factory's unit run after round 3

1 failed, 2013 passed, 69 skipped (rc 1, not killed): `tests/test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere`.
The lease history was `['expired', 'ack']`, not `['ack']`. Not fixed here (lesson-13). The brief said to fix the code,
but the code at fault is outside this gap. `git diff main...HEAD --stat` on `ergostat/leases/`, `ergostat/spec/engine.py`,
`ergostat/daemons/` and `tests/test_leases.py` is empty, and the test's model has no `library:` or `uses:` line. Run
alone here, it passes (1 passed, 3.3 s). Its lease has a 1 s TTL. The only renewals are the events the run writes
through `$ERGOSTAT_CMD event`, each a new Python process, 0.4 s apart. Under the whole suite at `-n 8`, one process
start plus the sleep can go past 1 s of silence, and then the watchdog rightly expires the lease. That is
lesson-10: either event writes really are slow under load, or the test's 1 s margin is too thin. It needs its own gap,
not a lease change inside a library gap. This is the third unrelated timing result in three full runs
(`test_warm`, a cut-off run, now `test_leases`), and each test passed alone.

**Left:** run the unit suite and the four browser files again. If this lease test also fails on main under the same
load, it is not this branch's.

### Round 4

No code changed. The review's two findings were both answered in round 2: `out:` is limited to the chain's own parts
(`trust._out`), and main is merged. Main is still an ancestor of HEAD: the factory's merge ec483c7a brings in main at
2388572a, and `git log HEAD..main` is empty. That merge changes nothing in `ergostat/library/`, `ergostat/spec/load.py`,
`ergostat/leases/` or `tests/test_leases.py`. `git diff main...HEAD` is still only this gap's 11 files. Nothing under
`ergostat/library/` or `ergostat/spec/` marks a library untrusted except this branch's map form, so point 1 stands.

Run here, after the merge: `tests/test_library_trust.py` (46 passed), `tests/test_templates.py` and
`tests/test_modelling_template.py` (unchanged, passed), and `tests/test_leases.py` alone (20 passed). That includes the
watchdog-renewal test that failed under load in the last full run (lesson-10 and lesson-13: it is outside this gap).
Ruff is clean. **Not run here:** the whole unit suite and the four browser files. They are left to the factory, under
the watchdog.

**Left:** run the unit suite and the four browser files under the watchdog. If the lease test fails again under load,
compare it with a run on clean main before holding this branch on it.

### Round 5

- **The merge (lesson-7).** The factory's merge of main at 0216e0e5 conflicted in `docs/SPEC.md`'s findings list.
  Resolved in b899163e, keeping both: main's new `about-missing-part`/`about-unknown` findings and the paragraph on
  open items' ids, and this branch's wording of `template-library` (an untrusted template not used because a trusted
  one has its name). Nothing else conflicted. Main added param `min`/`max` (templates.py, expand.py) and
  `Problem.items` (load.py); none of it marks a library untrusted, so point 1's map form stands.
- **The merge brought a key the allowlist did not classify.** Main's item `about:` (SPEC §5a, *About*) made
  `test_every_compile_key_classified` fail with `items.about` unclassified, which is what that test is for. It is
  now allowed as a scalar in `trust.ITEM`: it names a field holding the parts an item is about, compile checks it
  is a field name folded by replace, and only `check` reads it to report findings; it starts and sends nothing. If
  the owner would rather refuse it, it is one entry turned to `NO`.
- **Run here, after the merge:** `tests/test_library_trust.py` (46 passed), `tests/test_templates.py` and
  `tests/test_modelling_template.py` (40 passed, unchanged). Ruff is clean. **Not run here:** the whole unit suite
  and the four browser files, left to the factory under the watchdog.
  Size: 287 net lines outside tests and docs (budget 330).

**Left:** run the unit suite and the four browser files under the watchdog.
