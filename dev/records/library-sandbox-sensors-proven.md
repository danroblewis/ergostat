# library-sandbox-sensors-proven: an untrusted library's sensor `run:` runs only through `ergostat.sandbox`, with the policy proven by unit tests
depends-on: [library-provenance-join-1]

## Definition of done
This lands the built work of the parked `factory/library-sandbox-sensors` (its record's items 1–9 and its round-2 nested-marker fix), with that branch's code merged with main.
- A sensor `run:` runs on the owner's shell only when compile proves it is the owner's or ergostat's (an allowlist). Otherwise it goes through `sandbox.run` with:
  - `hosts={}`, `env={}`, and only the template folder readable;
  - a work folder under `<state>/library-work/` with a checked name, and a marker kept outside that folder;
  - a timeout of at most 120 s, and at most 4 runs at once, counted under one lock, with an escaped run keeping its slot.
- When no sandbox is available, nothing runs. A reading that did not happen records nothing. A sandboxed run cannot relay a message. A daemon from a library is refused `library-unsandboxed`, and the sensing view says `, sandboxed`.
- What runs is proven without a live sandbox. A captured `Policy` and argv are asserted for no hosts, empty env, a read list holding only the template folder, and the timeout ceiling. That the sandbox enforces a given `Policy` is left to `tests/test_sandbox_attacks.py`, and SPEC says so rather than claiming more.
- The four live-sandbox tests are kept and skip without a backend. The report says where they ran or that they did not.

## Relation to other work
- library-sandbox-blocks (in the graph): runs library blocks in the sandbox. This sub-gap stays out of `expand.py`.
- library-fetch-load: untrusted fetched libraries reach this path through the same untrusted flag.

## Files to touch
- `ergostat/library/runs.py` (new)
- `ergostat/spec/ir.py`
- `ergostat/spec/compile.py`
- `ergostat/spec/engine.py`
- `ergostat/sensing.py`
- `docs/SPEC.md`
- `docs/SECURITY.md`
- `docs/GAPS.md`
- `tests/test_library_sandbox_sensors.py` (new)

## Risks
- lesson-3: an unknown provenance, a `None` value for `run_in` or an exception must route to the sandbox, never to the owner's shell.
- lesson-1: the slot check and the slot take must happen under one lock.
- lesson-8: say only what the captured Policy proves, and point to the sandbox's own tests for enforcement.

## Acceptance tests
- `tests/test_library_sandbox_sensors.py::test_unknown_provenance_is_sandboxed`: `where=None`, a missing use, a `Where` subclass, a raising verdict and `run_in=None` each route to the sandbox.
- `tests/test_library_sandbox_sensors.py::test_policy_captured`: the `Policy` passed to `sandbox.run` has `hosts=={}`, `env=={}` and a read list holding only the template folder, even when the template names a host. A 99999 s timeout becomes 120.
- `tests/test_library_sandbox_sensors.py::test_slot_check_and_take_hold_one_lock`: with a cap of 1, a second `_slot` started in the window between check and take is refused.
- `tests/test_library_sandbox_sensors.py::test_no_sandbox_no_run`: with no backend, nothing runs and no measurement is made.
- `tests/test_library_sandbox_sensors.py::test_nested_remake_under_another_library_clears_work_folder`: switching the library above a nested instance, or changing its file, clears the folder, even with a forged marker inside it.
- `tests/test_library_sandbox_sensors.py::test_owner_file_sensor_runs_as_owner`: a `run:` in the model file runs with `callback_env` as today.

## Size budget
220 net lines
size: L (confidence: medium)
