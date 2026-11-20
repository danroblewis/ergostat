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
