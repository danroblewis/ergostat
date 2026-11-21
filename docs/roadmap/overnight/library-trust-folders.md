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
