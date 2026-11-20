# local-settings: per-machine settings beside a tracked model, never in it

depends-on: []

Branch `local-settings`, from main. Asked by the coordinator after the factory's first upgrade: the instance's `web:`
section (a public tunnel name, open: read) is a per-machine setting, but `web:` is allowed only in the model's main
file, so an upgrade that places the repository's model drops it (the owner's page went 403) and the factory turns the
edit into a gap that would commit a private hostname into the public repository.

## Definition of done

An untracked file beside the main model, `ergostat.local.yaml`, is read after the main file and may set per-machine
sections only: `web:`, `intake:` (bind), and other keys SPEC lists as per-machine; any other key there is an error
from `check` naming the file. It is never required, is listed in `.gitignore` for the repository, and its settings show
in `check` with their source. The factory's upgrader keeps the instance's `ergostat.local.yaml` across a switch and
never turns it into a model-edit gap. The ergostat-on-ergostat instance's `web:` moves there.

## Acceptance tests

- `tests/test_local_settings.py::test_web_from_the_local_file_is_used`
- `tests/test_local_settings.py::test_a_model_key_in_the_local_file_is_an_error`
- `tests/test_local_settings.py::test_the_local_file_is_optional`
- `tests/test_factory.py::test_a_switch_keeps_the_local_settings_and_makes_no_gap_of_them`

## Size budget

200 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built (43 net lines outside tests, docs and dev). No one was there to ask, so these are the choices I made, each the
easiest to undo:

- The per-machine settings are an allowlist (`PER_MACHINE` in `ergostat/spec/load.py`): `web:`, and under `intake:`
  only `bind:` and `allow:`. `hooks:` are part of the model, so in the local file they are an error
  (**not-per-machine**), like any other key. Widening the list is a one-line change, and SPEC §2 lists it.
- The local `web:` replaces the main file's whole; the local `intake:` keys go over the main file's (its hooks stay).
  When the main file's `intake:` is malformed, it is left as written so that its own error still shows.
- The local file is not one of `spec.files`, so no proposal or template author can edit it. The engine's reload stamp
  (`model.stamp`) follows it, so editing or creating it reloads the model.
- A last-good-model snapshot made before this code never looked for the file. When that snapshot is replayed, the
  file counts as absent, which is how that model ran.
- The upgrader (`dev/bin/live.py`) already placed and compared only `ergostat.yaml` and `dev/`. The new factory test
  pins that down and was seen to fail when the local file was added to the comparison.

Left, outside the repository: the running instance's `web:` was only ever in the instance's own copy
(`~/ergostat-live/instance/ergostat.yaml`, dropped by the upgrade). The repository's model has no `web:`. Moving it
means writing `~/ergostat-live/instance/ergostat.local.yaml` on the coordinator's machine (dev/README.md, "Start it",
shows how), which cannot be done from this container. `origin/main` was not merged: this clone has no `origin`, and
its `main` is the branch's base.

The factory's `unit` run after this failed with no test output: the log ends at uv's "Installed 1 package", with
neither a pytest line nor `suite_watch.py`'s closing JSON line, which it prints even when it kills a run. So pytest and the
watchdog were both gone before either wrote anything, most likely because the suite's container was stopped from
outside. No failing test is named. Each file the change can reach was run alone (`-p no:randomly`) and passed:
test_local_settings, test_factory, test_cli_fallback, test_spec_compile, test_web_access, test_intake, test_model,
test_reload_safety, test_reload_in_place, test_reload_soak, test_spec_watch, test_spec_schema, test_daemon_docs,
test_parity, test_coherence. Ruff is clean. The whole suite under `-n 8` was not run here: the house rules leave that to the
factory's watchdog. So no code was changed for this failure; the next `unit` run should show whether it happens again.
