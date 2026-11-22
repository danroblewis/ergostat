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
