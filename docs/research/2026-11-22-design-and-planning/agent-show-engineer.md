# Owner item 19: an Agent show page (engineer's notes, 2026-11-22)

Code root below: DESIGN/ergostat = <workdir>/design/ergostat

## What an "agent" is in the code

- A row on /agents is a **block**, not a `[agents]` machine: `ergostat/spec/legacy.py:49-58` makes one `mdl.Agent` per
  block, its kind from the block's `agent:` machine (`spec.agents[b.agent].kind`), else a built-in's rung
  (`Block.builtin_rung`, `ergostat/spec/ir.py:737-743`: every built-in is `rule`, a judge `program`, an intent judge
  with a model `narrow-ai`), else the type (`legacy.py:13`). The ladder: `RUNG_NAMES` in `web/static/util.js:245`,
  `AGENT_KINDS`/`KIND_RUNS` in `ergostat/spec/compile.py:83,114`.
- What is shown of it: `mdl.Agent` (`ergostat/model.py:165-186`: name, kind, command, every, on, description, cron,
  timeout, parse). The block's own definition (`Block.params`: `prompt`, `run`, `ask`, `goal`, `until`, `table`,
  `expr`, `model`, `tools`, `read`, `actions`, `takes`, `lease`, `on`/`emits`) never reaches the page.
- API: `/api/agents/NAME` in `ergostat/web/server.py:557-575` returns `a.__dict__`, the snapshot row, recent runs, the
  log tail and absolute `log_path`, loads, use. It already looks up the block (`server.py:567`) but only for its daemon.
- Panel: `openAgent` in `ergostat/web/static/details.js:218-252` (description, command, runs, fills, in window,
  durations, daemon, absolute log path, runs chart, cost, recent runs, log tail). The list: `pageAgents`
  `web/static/pages.js:71-127`, row click opens the panel (`pages.js:100`).
- No page route: `UI_PAGES` `web/server.py:35` and the router `web/static/util.js:498-512` have no `/agent/NAME`;
  `http://127.0.0.1:8791/agent/work` is a 404 (shots/plan-agentshow-route-today.png).

## Reproduced on :8791 (ticket-factory)

- `work` is `type: ai, prompt: prompts/work.md, run: python3 bin/step.py work` (demos/ticket-factory/steps/03-work.yaml).
  Its panel (shots/plan-agentshow-work-panel.png) shows `Command python3 bin/step.py work`, "Runs: not run by ergostat"
  (wrong; Q38), the absolute log path (Q12), and no prompt, no program, no takes/lease/workspace.
- `keep-located-worked` (rule, the implied onoff) panel (shots/plan-agentshow-rule-panel.png): "implied by work's goal:
  located-worked", nothing about the pattern (on while located > 0, released at <= 0).
- `improver` (ai) runs `.venv/bin/python -m ergostat.library.run standin improver`; its prompt is a package file
  (`${folder}/modeller.md`, `ergostat/library/templates/modelling/template.yaml:364-395`), outside the project, so the
  existing `/file/` route (`server.py:828-842`: model dir and project dir only) cannot serve it.
- `fixer` (program) runs `python -m ergostat.library.run modelling rules`: its source is an ergostat module.
- No demo has a `narrow-ai` or `decision` agent (kinds counted over /api/agents of :8791-:8797: person, ai, program,
  rule only). Acceptance for those rungs needs a fixture or a demo change.
- :8798 (the factory) did not answer `GET /` within 8 s nor `/api/agents` within 150 s at the time of the walk, so the
  large case could not be timed (feeds owner item 2). /api/agents on the demos: 0.2 s to 1.1 s.

## What already exists and should be reused

- Markdown and code rendering: `md()`, `code()`, `render()`, `fileView()`, `CODE` map in `web/static/pages.js:180-268`
  (marked with raw HTML escaped, highlight.js with bash, python, yaml, json, js, go, rust, sql... bundled in
  `static/highlight.min.js`). Item fields already show files this way.
- The rule pattern in words and MathML: `BlockDiagram.block_fn` `ergostat/blockdiagram.py:1023-1140` returns `says`
  ("an on-off controller (a relay with hysteresis): u = 1 while y_located > 0, u = 0 once y_located is back to <= 0"),
  `math`, and `rows` (threshold, releases at) for onoff/compare/alarm/timer, expr/lookup/select/schedule/counter,
  proportional, delay, limit, and machine blocks. Blocks' panel renders it (`static/blocks.js:1010-1030`, `mathml()`).
  The show page uses the same words, so the Blocks diagram and the Agent page never disagree (Q65 owns the words).
- What a controller decided, grouped: `state.decisions` `ergostat/state.py:459-469`, and the ladder hint
  (`state.py:592-603`: "decided X 9 of 10 times: a rule could fill it").
- Prompt resolution as the engine does it: `spec.root / prompt`, inline text when it has a newline
  (`ergostat/spec/engine.py:917-926`); compile's check `spec/compile.py:1497-1500`.

## Per rung, what "how it works" is

| rung | today's data | shown |
|---|---|---|
| person | `ask` | the ask text, as Markdown |
| ai | `prompt` (file or text), `run`, `model`, `tools`, `read`, `actions`, `workspace`/`workdir`, `context` | the prompt rendered; the wrapper program highlighted when `run` names a file |
| narrow-ai | an ai block on a narrow-ai machine, or the intent judge with a model | the prompt plus its contract (takes, out ports, emits, tools, model, max cost, timeout); the declared "specification" is a design question |
| decision | a program on a decision machine (`KIND_RUNS`) | the program, its out ports, and what it decided (state.decisions); declared fixed answers do not exist yet |
| program | `run` or `daemon` | the program's files, highlighted (`bin/step.py`, `bin/ai.sh`, `python -m ergostat...` module) |
| rule | built-in params (`goal`/`until`, `above`/`below`, `table`, `expr`) | block_fn's says/math/rows; a table as a table |

## Sizes and risks

1. **Page and definition** (incremental): route, a new `static/agent.js`, the API adding the block's definition and
   law, the panel's sections factored so the panel and the page share them. Risk: merge conflicts with the filed
   quick fixes on `openAgent` (Q38, Q39, Q40, Q41, Q12), which edit the same 35 lines; factor them into one
   function and keep the panel's content. `BlockDiagram(spec, snap)` builds its classification each call
   (`blockdiagram.py:114-122`); on the big models build it once per snapshot or time it (budget below).
2. **Its own files** (incremental): an allowlisted reader. Risk: it is a file read from a web request. Only the files
   the block names (its prompt, the files on its `run` / daemon `run`, a `python -m` module), resolved where the engine
   resolves them, only under the model's root, the project dir, the ergostat package or a library template's folder,
   never the state dir under a public name, capped at `FILE_LIMIT`, shown by a relative name (never `/private/...`,
   Q12). The static snapshot (`web/snapshot.py:33-44`) must include it or say "not in the snapshot".
3. **Narrow AI specification and decision means** (large): nothing declares either. Needs a proposal: declare
   `answers:` on a decision block? what a narrow AI's specification is beyond its prompt and contract? a fixture.
   Also settles R12 point 5 (Agents after R4) now that the owner asked for the page.
