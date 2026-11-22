# agent-spec-api: An agent's answer carries what it is: its block's definition, prompt and program files, law, machine and decisions

depends-on: []

Problem: /api/agents/NAME (ergostat/web/server.py:557-575) returns only the mdl.Agent dataclass (model.py:165-186: name, kind, command, schedule), runs, a log tail and use, though it looks the block up at :567. On :8791 the ai block `work` has prompt: prompts/work.md and run: python3 bin/step.py work (demos/ticket-factory/steps/03-work.yaml) but the answer says only the command (spec/legacy.py:53 keeps a prompt only without a run, cut to 60 chars). The rule keep-located-worked carries no law though BlockDiagram.block_fn (blockdiagram.py:1023-1140) computes it for Blocks. The person approve has no ask. fixer's command is an absolute .venv path; improver's prompt is a package file (library/templates/modelling/template.yaml:364-395) the /file/ route (server.py:828-842) cannot serve. Decision tallies (state.decisions, state.py:459-469) are not reachable per agent.
Change: a new module ergostat/web/agent_spec.py adds `spec` to /api/agents/NAME: type, implied and implied_by, where ({file relative to the model folder, line}), source (the block's YAML as written; null when implied), params as written (prompt, ask, run, daemon, parse, model, tools, actions, read, workspace, emits, on, goal, until, expr, table, takes, pool, lease, ...), prompt_text when inline, law (block_fn: says, math, rows; built once per snapshot), machine (its agents: entry), decisions (state.decisions over the window for the controllers it fills, plus the ladder hint, state.py:592-603), rung_why, own ({module, doc} for `-m ergostat.<module>`, never the interpreter path; default, no owner question: ergostat's own module sources are named with their docstring, not shown), and files: [{name, role: prompt|program|wrapper, format}]. A guarded route GET /api/agents/NAME/files returns each file's text: the prompt resolved as the engine does (spec/engine.py:917-926), run tokens that are existing files (interpreters skipped). Each file must lie under spec.root, the project dir or a library template folder; never the state dir under a public name (as _file does, server.py:834); at most FILE_LIMIT and 8 files; names always relative ('prompts/work.md', 'ergostat's own: library/templates/modelling/modeller.md'). web/snapshot.py:41 adds agents/NAME/files.
Definition of done:
1. /api/agents/work on ticket-factory has spec.files with {name: 'prompts/work.md', role: 'prompt', format: 'markdown'} and bin/step.py, and spec.params.takes.kind == 'ticket'.
2. /api/agents/keep-located-worked has implied true, implied_by 'work' and a non-empty law.
3. /api/agents/fixer has spec.own.module set and no string containing '/.venv/' or '/private/'.
4. A run naming ../../etc/passwd or an absolute path outside the roots is listed 'not shown: outside the project' and never read.
5. A decision-rung agent (examples/docs-fresh page-picker) has decisions {count, kinds}.
6. /api/agents/NAME stays under 300 ms on :8796 and :8797 (median of 10).
Files: new ergostat/web/agent_spec.py, ergostat/web/server.py, ergostat/web/snapshot.py, tests/test_agent_spec.py.
Acceptance tests: unit tests on a tiny model with one block of each type (ai with prompt file and run, ai inline prompt, narrow-ai, decision, program bin/x.py, program -m ergostat.library.run, implied onoff, expr, lookup, person with ask) asserting the fields, roots, traversal, size cap.
Budget: 260 net lines (tests not counted). If the builder finds it over 300, the file route is split off as its own gap and said to the Coordinator.

Milestone: agent-show-page. Owner items: 19. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built: all six points, with tests in tests/test_agent_spec.py (8 tests, all pass). Points 1, 2, 3 and 5 are tested on
copies of examples/ticket-factory and examples/docs-fresh (fixer there is the first agent whose name ends in `fixer`).
Point 6 was not measured on :8796/:8797, which this container cannot reach. `test_an_agents_answer_is_quick` checks
the same bound in-process on a copy of ticket-factory instead (median of 10, marked serial).

Decisions taken without the owner, each easy to undo:
- The state directory is refused under every name, not only public ones: the files route cannot tell who is asking,
  and being stricter is the safer way to be wrong.
- For a run, a run file of an ai block has role `wrapper` (it wraps the session) and one of any other block has role
  `program`. A path in a run that lies outside the roots is listed as written (an absolute one by its base name only),
  is never stat'ed and is never read. The files route checks each path again at the moment it reads it.
- A block a template made has its `where` and `source` at its `use:` entry (what the owner wrote). Its `params` are
  the compiled keys (takes, on and pool added), because the template text has unexpanded `${...}` values. `implied_by`
  is the first block the implied onoff commands.
- Every string in `spec` has these absolute paths taken out: the interpreter becomes `python`, ergostat's package
  folder becomes `ergostat`, and the model folder becomes a relative path. The old fields of the answer (`agent.command`,
  `log_path`) are left as they were.
- `decisions` sums the controllers the agent fills and adds `controllers` and the ladder `hint`. It is null when the
  agent fills no controller.

Overrun reason: 273 net lines against 260 (under the 300 split line), because the source extraction (its YAML as written, parsed with the spec's YAML 1.2 loader so `on:` stays a key) and the second check made at read time take about 20 lines more than planned.
