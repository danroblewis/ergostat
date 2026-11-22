# Tests: fixtures worth knowing

**`factory_state`** (tests/conftest.py): a factory-size state directory, written by `scripts/factory_fixture.py OUT
--seed 1` (byte for byte the same for one seed and `--end`), built once a session into a temporary directory, with
its record ending at the hour the session started, and skipped under a `-m fast` run. It holds the factory's
measured shape: 25 model files, 60 goals in 8 systems (two made by `use: modelling` and `use: upkeep`), 260 sensors,
37 machine blocks (declared, filled by a program), 8 item kinds with 1,500 items (`gap`: 430, most of them in
`depends_on` chains, 40 parked (paused), 10 dead), 30 sealed segments of events over 24 h (mostly the machine blocks'
runs), about 2,000 lease attempts, 60% of them given back uncounted at the gated block `gap-approved`, a reading a
minute of every sensor, the goal `gap-prompt` off for a planted 20 minutes six hours before the end, and one upkeep
goal off for the last two hours. `factory_state.serve()` starts a page server on it (a context manager giving its
URL); `factory_state.project()` opens it. Every model part and block is a stand-in: nothing calls an AI or costs money.

Numbers taken on the live factory (`:8798`) in a PR are measured by hand on a copy of its state directory, never in
CI: its record holds the owner's work and cannot be shipped. Compare them with the same measurement on this fixture.
