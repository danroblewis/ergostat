# goal-state-says-its-system-and-upkeep: Each goal's state says its system and whether it is the modelling system's own, and one server function makes the goals-off counts

depends-on: []

Problem: the headline counts every goal with status off, computed in the browser (ergostat/web/static/util.js:364); the switcher counts off and open (ergostat/projects.py:44-48), a second definition. A goal's state in the snapshot (ergostat/state.py:304-312) carries neither its system nor whether a once template made it, so filed Q14 (headline), Q16 (rows by system), Q42 (side list groups) and Q13 would each invent a predicate. On :8791, :8792, :8796 and :8797 the red '2 loops off' is entirely modelling's requests-handled and model-fits (shots/plan-goalvocab-8791-loops.png, plan-goalvocab-8792-phone-home.png). The predicate exists: ergostat/spec/ir.py:336 once_made(spec, x). Precedent for setting goals apart: state.py:625-629 skips a remote's goals.
Change: (1) beside once_made, one named set OWN_TEMPLATES = {'modelling'}: exactly the owner's decision. The upkeep template's goals (index-files-few and others), repair and interventions stay in the headline until the owner says otherwise (the one open question; adding a name is a one-line edit). (2) state.snapshot adds to each goal's entry `system` (spec.goals[name].system; null without a spec) and `upkeep: '<template>'` when the goal was made by a template in the set (field absent otherwise). (3) one function state.goals_off(snapshot) -> {system: n, unknown: n, open: n, own: {modelling: n}} is the only place the counts are made; /api/status carries it as goals_off and projects._row uses it (upkeep_off: the sorted own goals off or open, left out of off). Key names loops, off and unknown stay: remotes, snapshots and status --json read them. (4) one SPEC line: what upkeep means and that the API's `loops` are the goals' states.
Definition of done:
1. On a small spec with `use: modelling` and one system goal, each off (a seeded fixture, not a live demo, whose upkeep goals other gaps make hold): loops['requests-handled'].upkeep == 'modelling', the system goal has no upkeep field, every goal has a non-null system, goals_off.own.modelling == 2 when both modelling goals are off.
2. A goal made by the upkeep template has no upkeep field and is counted in goals_off.system.
3. /api/projects: that project's row has upkeep_off listing modelling's goals and they are not in off.
4. /api/status and projects._row both call state.goals_off (no second count on the server).
5. No reader-facing change; existing tests pass unchanged.
Files: ergostat/spec/ir.py, ergostat/state.py, ergostat/web/server.py, ergostat/projects.py, docs/SPEC.md, tests/test_runner_and_state.py or a new small test.
Acceptance tests: the unit test of points 1-3 on the small spec; a test_graph_cli_web assertion on /api/status of the fixture.
Budget: 50 net lines. For the Coordinator: filed Q14, Q16, Q17 and Q42 are blocked by this gap and must read these fields, not their own test.

Milestone: goals-not-loops. Owner items: Decision: the modelling system's goals come out of the headline (shown beside it). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built in round 1; nothing in the definition is left. Where nobody could be asked, I took the most reversible option each time:

- `upkeep_of(spec, x)` in `spec/ir.py` takes the template's name from `spec.uses[instance]["template"]`, and only for
  a part that `once_made` already accepts (a once library template, not an owner-folder one).
- `goals_off` counts `unknown` over every goal, upkeep goals included, so the row's `unknown` list stays as it was.
  Only upkeep goals that are off or open move to `own`. If the owner wants unknown upkeep goals moved out too, that is a one-line change.
- `goals_off(snap, names=True)` gives the same keys holding sorted names, so `projects._row` gets its lists from the one
  function. `system` counts goals that are off and `open` goals that are open (neither includes upkeep goals). The row's `off` is both, as before.
- The browser headline (util.js:364) is unchanged, because point 5 says no reader-facing change; Q14 is the one to read `goals_off`.
- Point 3 is tested through `projects.known`, which `/api/projects` serves, not through the HTTP route.
- Acceptance tests: `tests/test_goal_upkeep.py` covers points 1-3 on a seeded small spec with `use: modelling`, `use: upkeep`
  and one system goal. The /api/status test is
  `tests/test_graph_cli_web.py::test_api_status_counts_the_goals_off_with_modellings_own_beside_them`.
  Both failed when `upkeep_of` was made to return None, and the first also failed with `upkeep` added to `OWN_TEMPLATES`.
