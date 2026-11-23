# conformance-model-formats-list: ergostat's conformance list: model formats, YAML, TOML, served model and XMILE both ways

depends-on: [conformance-list-files]

# conformance-model-formats-list: `dev/conformance/model-formats.yaml` and its checks



The proposal's section 6, model formats, has five cases:
- `ergostat-yaml`, expected met (`ergostat/spec/load.py:171`);
- `ergostat-toml`, expected met: `ergostat convert` writes a model that compiles (`ergostat/spec/convert.py:1-9`, `ergostat/cli/__init__.py:153`);
- `served-model`, expected met: the remote answer says `ergostat-model/1` (`ergostat/remote/serve.py:12`);
- `xmile-export`, expected unmet (◻ at `docs/DISCIPLINES.md:21`; nothing under `ergostat/` names XMILE);
- `xmile-import`, expected unmet (one-way proposed, `docs/research/sre-control-systems.md:1281-1282`).

The filed gap `export-dynamics-xmile` (ready) builds the export. This list is not that work: its `xmile-export` check is what will flip to met when that gap merges, the first real `conformance-gained`.

## Change
`dev/conformance/model-formats.yaml` (`list: model-formats`) and `dev/conformance/checks/formats.py CASE`:
- `ergostat-yaml`: `ergostat check` on every `examples/*/ergostat.yaml` exits 0.
- `ergostat-toml`: every old TOML example converts into a temp dir and compiles.
- `served-model`: the served model answer, built in-process, says `ergostat-model/1` and names every stock of `examples/image-squeeze`.
- `xmile-export`: it looks for the export entry point (the CLI subcommand or module the export gap names). If there is none, it exits 1. If there is, it exports image-squeeze and parses the result with `xml.etree`: XMILE 1.0's namespace, one `<stock>` per stock, one `<flow>` per flow, and every `<eqn>` free of ergostat-only syntax.
- `xmile-import`: a 2-stock, 1-flow XMILE fixture kept beside the checks becomes a draft model whose stocks, flows and causes' signs match. It exits 1 while there is no importer.

An absent feature is unmet (exit 1), never broken. Broken (exit 2) is only the check's own failure.

## Definition of done
1. The file parses with the reader and declares exactly these 5 cases, all `asked: true`.
2. Each check run on main gives the result recorded in the record, with any difference explained.
3. Each check expected met is shown able to fail against a broken copy (an example with a bad reference; a served answer with its version changed): it exits 1.
4. The XMILE checks test structure, not byte equality, so the export gap's own choices of layout do not make the case unmet.

## Files to touch
`dev/conformance/model-formats.yaml` (new), `dev/conformance/checks/formats.py` (new), `dev/conformance/checks/fixtures/small.xmile` (new), `tests/test_conformance_lists_ergostat.py`.

## Risks
- lesson-9: each check is shown able to fail.
- Do not write any part of the XMILE export here. That is the filed gap's.

## Acceptance tests
- test_model_formats_list_parses_with_five_cases
- test_xmile_checks_exit_1_without_the_feature
- test_each_met_format_check_fails_on_a_broken_copy

## Size budget
At most 170 net lines outside `tests/` (dev/ counts).

Area: conformance. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:22).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 14:22).

Its runs failed past their attempts (a dead letter):
- attempt 2: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 3: nack given back
- attempt 4: nack exited 1
- attempt 5: nack the run ended with gap/conformance-model-formats-list still parked

## Where it stopped

Built, round 1 (implementor, 2026-11-23): `dev/conformance/model-formats.yaml` (the 5 cases, all `asked: true`),
`dev/conformance/checks/formats.py` (`python3 dev/conformance/checks/formats.py CASE [ROOT]`),
`dev/conformance/checks/fixtures/small.xmile`, and `tests/test_conformance_lists_ergostat.py` (the 3 named tests plus
4 more: the results on main, broken-not-unmet, and the two XMILE checks against stand-in modules).

Each check run on main (`test_checks_on_main_give_the_recorded_results`), beside section 6's expectations:

| Case | Expected | Got on main | Note |
|---|---|---|---|
| `ergostat-yaml` | met | met (exit 0) | `ergostat check --no-coherence` on all 20 `examples/*/ergostat.yaml` |
| `ergostat-toml` | met | met (exit 0) | the 12 old examples are `tests/fixtures/toml/*.toml` (none is left under `examples/`) |
| `served-model` | met | met (exit 0) | |
| `xmile-export` | unmet | unmet (exit 1) | no `ergostat/xmile.py` |
| `xmile-import` | unmet | unmet (exit 1) | no importer |

No differences. Seen able to fail (lesson-9): first-loop with `out: flow.nowhere`, and first-loop.toml with its
valve on `flow = "nowhere"`, both exit 1 (a good copy of each exits 0); the served answer with `FORMAT`
`ergostat-model/2`, or with one stock left out, exits 1. Four mutations of the checks were each seen to fail a test,
then reverted: the served format test removed, TOML compile errors ignored after convert, the `<eqn>` syntax scan
turned off, and causes read without their sign.

Choices the definition left open, each taken the more reversible way:
- **The export entry point.** The export gap's brief names a new module, `ergostat/xmile.py`, but not its function.
  If the module is missing, the case is unmet. If it is there, the check calls the first of `export`, `to_xmile` or
  `write` with the compiled spec of image-squeeze, and takes text, bytes or an `Element` back. If the module is
  there but has none of those functions, the case is *broken* (exit 2, "update this check"), not unmet, so a
  renamed function cannot hide a built export. When that gap merges, its own name for the function should be added
  to `EXPORTS` if it differs.
- **What the XMILE checks compare.** Structure only (definition item 4): the root's tag in XMILE 1.0's namespace,
  and the `<stock>` and `<flow>` names, compared as sets with `-`, `_` and spaces taken as the same character.
  Every `<eqn>` must hold no `stock.`/`flow.`/`auxiliary.`/`parameter.`/`goal.`/`block.` reference, no `${`, and no
  hyphenated name from the model written as it is. Order, whitespace, headers and vendor elements do not count
  (tested).
- **The importer entry point.** Nothing names it. The check looks for `ergostat.xmile.draft`/`from_xmile`, then
  `ergostat.spec.discover.from_xmile` (named like `from_prometheus`). It passes the fixture's text and reads back
  YAML text, a `(text, notes)` pair or a mapping. The draft must have stocks `backlog` and `done`, one flow `work`
  from backlog to done, and `driven-by` exactly `+backlog` and `-done` (an unsigned cause does not match).
  Auxiliaries are not compared: the definition's fixture has 2 stocks and 1 flow, and no auxiliary.
- `ergostat check` is run with `--no-coherence`, so the result does not depend on any machine's record.
- Nothing to check is broken (exit 2), never met: no examples, no TOML fixtures, or image-squeeze not compiling.
- `test_checks_on_main_give_the_recorded_results` takes about 100 s, almost all of it in `ergostat-yaml`, which
  runs `ergostat check` once per example in turn (each can wait up to 5 s for the extreme-conditions tests). It is
  kept so that item 2 is checked by a test, not by one run by hand. It could be dropped from the unit suite if that
  time is too much.

Overrun reason: the budget of 170 lines counts dev/, and the three files under dev/conformance/ come to 218 lines (formats.py 180, the list 25, the fixture 13), about 50 of them blank lines and docstrings. The five checks, the broken-copy ROOT argument and the stricter met/unmet/broken split need them. The factory's own net-line count (fac.net_lines) leaves dev/ out, which gives 0.

## Where it stopped

Round 2 (implementor, 2026-11-23). The only finding, which was blocking (formats.py:105-106, lesson-9 and lesson-8):
the check called the export as `fn(spec)`, but the export gap's built branch defines `ergostat/xmile.py`
`export(p, snap: dict, system=None) -> str`. When that gap merged, the case would have been broken, not met.
- **Changed:** `xmile_export` now calls `ergostat.xmile.export` the way it is built: `p` is a `store.Project` over
  `examples/image-squeeze` (`model.load`), with its store in a temp dir (`note=False`, so nothing is written to the
  repository or to `ERGOSTAT_HOME`), `snap` is `state.snapshot(p)`, and `system` is `None` (the whole model). The
  answer is read as text, bytes or an `Element`, as before. The guessed list of names (`EXPORTS`: `export`,
  `to_xmile`, `write`) is gone. If the module is there but has no `export`, the case is still broken (exit 2,
  "update this check").
- **Tests:** the stand-ins in `test_xmile_export_check_reads_structure_not_bytes` now have the real signature
  (`export(p, snap, system=None)`). They read `p.model.spec`, assert that `snap` is a snapshot dict and `system` is
  `None`, and record that the project is image-squeeze. I put the old call `fn(spec)` back to confirm the test can
  fail: it failed, with "broken: TypeError: ... missing 1 required positional argument: 'snap'". Then I reverted it.
- **Not done:** the real module is not on `main` or in this clone, so the check has not been run against it. The
  signature comes from the review's reading of that branch. If the export gap changes it before it merges, this
  call has to change with it. The served route (`/api/export?view=dynamics&format=xmile`) was not used: its answer's
  shape is not on `main` either, and the module call is the narrower dependency.

Overrun reason: the budget of 170 lines counts dev/, and the three files under dev/conformance/ come to 221 lines (formats.py 183, the list 25, the fixture 13), about 50 of them blank lines and docstrings; round 2 adds 3 net lines to call the export with a project and a snapshot. The factory's own net-line count (fac.net_lines) leaves dev/ out, which gives 0.

## Where it stopped

Round 3 (implementor, 2026-11-23). The only finding, which was blocking (lesson-7): two tests pinned the export's
absence, so merging `export-dynamics-xmile` would have broken them. Only `tests/test_conformance_lists_ergostat.py`
changed. No check changed.
- **`test_xmile_checks_exit_1_without_the_feature`** no longer runs the check in a subprocess against the tree. It
  installs stand-ins first: an `ergostat.xmile` with `export` and `draft`, and `ergostat.spec.discover.from_xmile`.
  Both cases are shown met (0). Then it hides them inside the process (`sys.modules['ergostat.xmile'] = None`, and
  `from_xmile` deleted from `discover`) and calls `formats.main` for each case. Each must exit 1 with "no XMILE
  export" or "no XMILE importer". The result is the same whether or not `ergostat/xmile.py` is on main. Seen able to
  fail: with the hiding call taken out, the test failed (`find_spec` returned the stand-in's spec). Then I put the
  call back.
- **`test_checks_on_main_give_the_recorded_results`** expects `xmile-export` to be unmet (1) while
  `ergostat/xmile.py` does not exist, and met (0) once it does. It expects `xmile-import` to be unmet while none of
  the check's importer names (`formats.IMPORTS`) is callable, and met once one is. Neither case may be broken (2).
- **Not done:** I could not run the on-main test with the export present. The command that wrote a temporary
  stand-in `ergostat/xmile.py` into the tree (and used `sed` to mutate the test) was refused, so I did not try it
  another way. The met-when-present branch is covered only in-process, by the stand-ins above and in
  `test_xmile_export_check_reads_structure_not_bytes`.

Overrun reason: unchanged from round 2 (221 lines under dev/conformance/, all of it dev/, which the budget counts); round 3 changes only tests/.

## Where it stopped

Round 4 (implementor, 2026-11-23). The only finding was the conflict with main in
`tests/test_conformance_lists_ergostat.py`: main's conformance-diagrams-list added its own tests to the same file.
I kept both sides: one docstring for both lists, the imports of both, `ROOT` resolved the way main has it, and one
`load(path, name)` helper used by the branch's `formats` fixture and by main's `checks()`. The branch's tests come
first, then main's diagrams tests, unchanged. No check changed. All 21 tests in the file pass, and ruff is clean.

Overrun reason: unchanged from round 2 (221 lines under dev/conformance/, all of it dev/, which the budget counts); round 4 changes only tests/.
