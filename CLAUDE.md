# Rules for working on ergostat

> **Setting up ergostat for someone, rather than changing ergostat itself?** Read
> [docs/AGENT-GUIDE.md](docs/AGENT-GUIDE.md) first: how to turn the work a person describes into a model
> that runs and is the right shape, how to check it, and how to look at its diagrams before you call it
> done. Then [docs/MODELLING-WELL.md](docs/MODELLING-WELL.md): the craft that makes each of the three diagrams
> (Dynamics, Blocks, Process) look as a professional in its discipline would draw it. The rest of this file is for
> changing ergostat's own code.

Ergostat keeps work going. It is a tool for drawing a control-system boundary around whatever
someone wants to keep working, and for designing, seeing and running the control system inside it.
The settled terms are in `NOTES.md`; read it first.

The design as built is `docs/DESIGN.md`; the CLI review rounds are in
`docs/cli-rounds.md`. Build only what the owner asks for. A question about what a user would want
first is a discussion, not a request to build it.

## Invariants

These must not be broken without the owner's agreement, recorded in `NOTES.md` and said in the
commit.

1. **Work, not tasks.** Ergostat knows work: change in the world over time, seen as stocks and
   flows. It has no concept of task, ticket, issue or job, ships no unit of work, and treats none
   specially. Users build their own units of work as items.
2. **Three roles.** The control system is made of **sensors** (measure, never act),
   **controllers** (decide, to hold a setpoint) and **valves** (act). Nothing changes the world
   outside ergostat except through a valve.
3. **Agents fill roles; they are not roles.** An agent is whatever acts on the owner's behalf: a
   person, an AI agent, a narrow AI agent, a decision, a program or a rule. One agent may fill many
   roles. Filling a role never changes the role. Adding a role is designing the system, done by the
   owner or by the Supervisor on their behalf.
4. **Every agent shows its rung.** Never just "agent": always its kind (person, AI, narrow AI,
   decision, program, rule). A role whose agent is gone is retired, and that is shown as a success.
5. **The refactor path is the expected direction.** Roles start with the universal AI agent and
   move down the ladder, toward programs, rules and finally no work at all. The design must make
   each step visible and possible.
6. **Every agent is held to the same discipline**: measured, bounded, and acting only through
   valves the owner grants, whether it is a person or an AI.
7. **Disturbances are modelled.** A disturbance is an input no valve controls, measured or
   estimated. A residual (what the model fails to explain) is evidence, never silently ignored.
8. **One control system.** The diagram is one system that can be panned, zoomed and grouped.
   Disconnected parts are found by graph analysis, never separated by declaration.
9. **The diagram is primary.** Control-theory diagrams are a first-class part of the product, not
   an export. Everything else supports them.
10. **Events and metrics are kept apart.** Events (what happened: append-only, never edited) and
    metrics (time series: many, cheap) live in separate stores. Items are folds of events by id,
    rebuilt from the record.
11. **Defined and inferred stay distinguishable.** Everything in the model says whether it was
    declared or inferred from data, so that discovery can be added later without rewriting what
    people declared.
12. **Ergostat adds nothing of its own accord.** No built-in agents, no built-in units of work, no
    roles it was not asked for. An empty install runs nothing.

## Words

Use the terms in `NOTES.md` and no others for the same things: work, item, sensor, controller,
valve, disturbance, residual, agent, rung, retired, owner, Supervisor. Never "task", "worker" or
"machine" for these.

## Working here

- Python 3.12+, `uv`, the standard library only at runtime; the unit suite and `uv run ruff check` before every
  commit.
- **Testing.** Both suites run in parallel (pytest-xdist), under the watchdog (`scripts/suite_watch.py`: kills the run
  past 1,500 threads or 6 GB, and one worker past 2 GB), one suite at a time, never both at once:
  - unit (about 2 min; 12 serial): `uv run python scripts/suite_watch.py -- uv run python -m pytest -q -n 8 --dist worksteal`
  - browser (about 6 min; 21 serial): `uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python -m
    pytest -q -n 4 --dist worksteal tests/test_diagram_rendering.py tests/test_page_polling.py tests/test_items_page.py
    tests/test_page_refresh.py`
  - the serial fallback (a test that fails only in parallel, or a busy machine): the same without `-n ... --dist
    worksteal`, e.g. `uv run python -m pytest -q`.

  Don't raise the worker counts: 8 and 4 are what stays under the limits (measured in
  `docs/roadmap/overnight/fastsuite.md`). A test of 10 s or more is marked `@pytest.mark.slow`, so a parallel run
  starts it first. A test that fails only in parallel is first looked at as a race (in the test or in ergostat)
  and fixed; one whose time bound holds only on a quiet machine is marked `@pytest.mark.serial`, and the parallel run
  holds everything else back while it runs (tests/conftest.py). Never raise a time bound to pass under load. `scripts/demo_check.py` runs every demo in
  `~/ergostat-demos/` and checks its pages (with Playwright when installed).
  A definition whose acceptance is a repeated or loaded measurement (say "30 loaded runs of `-n 8 tests/x.py`") names
  it plainly. A factory session neither runs it nor works around that: it says "not run here". The factory runs it on
  the branch head with `python3 dev/bin/manage.py measure-runs gap/NAME --runs 30 --load 4 --tests "-n 8 tests/x.py"`
  (dev/README.md, *The pipeline manager*). The coordinator runs that by hand. When the pipeline manager calls it, it is
  asked in the inbox (`manager-measure`). The approval starts it detached, outside the manager's 1 h block, and the
  approver does not wait for it.
- **The container.** When Docker is up, heavy work runs inside it, under hard limits the kernel enforces (4096
  processes and threads, 12 GB, half the CPUs, no network but localhost): `scripts/in_container.sh CMD ...`, e.g.
  `scripts/in_container.sh uv run python scripts/suite_watch.py -- uv run python -m pytest -q -n 8 --dist worksteal`
  (docs/DEVELOPMENT.md has every standard run). **Preferred** there: the benchmarks (`scale_bench`, `latency_bench`,
  `daemon_bench`, `loadtest`), load and soak tests, the layout corpus, the unit and browser suites and `demo_check`
  (the benchmarks and the corpus are documented but not yet measured inside). The Linux sandbox's tests need
  `scripts/in_container.sh --sandbox` (Docker's syscall filter off, for bwrap; only for them). On Linux no test is
  expected to fail: a failure there is real. **When Docker is down:** the same commands on the host, under `scripts/suite_watch.py`
  as always. **On the host only:** the macOS sandbox tests (`tests/test_sandbox_attacks.py` exercises `sandbox-exec`
  only on macOS; run it on both when the sandbox changes), and anything that needs the owner's real credentials or
  services. This Mac has kernel-panicked three times from development work (two thread exhaustions in benchmarks,
  one `sandbox-exec` profile bug); the watchdog alone is not a hard limit. The container limits resources; it is
  not a security boundary (docs/DEVELOPMENT.md).
- The repository is on GitHub (danroblewis/ergostat); main must always work, since people install from it.
- Never write an employer's names (systems, services, metrics, labels, ticket types, people) into
  tracked files; use generic stand-ins.
- Commit only when the owner asks. End commit messages with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
