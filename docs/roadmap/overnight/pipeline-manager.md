# pipeline-manager: an AI block that watches over the pipeline, as the coordinator did by hand

depends-on: []

Branch `pipeline-manager`, from main. Asked by the owner: "in a previous setup we had a pipeline_manager agent that
watched over the pipeline. it would check if merges were stuck, and it would re-engage the implementor and review
cycle, it would also watch the merge queue and try to reduce the time it takes to merge overall... having a pipeline
manager triage the issues was important." Today the coordinator does it by hand, and records each time as an
`intervention.recorded`: pool-control parked on main's own test failures and continued (`continues`); a gap
re-approved after an environmental queue failure; parked branches seeded into the drop; the queue blocked by a failed
push and remedied; missing gaps filed. Each of those is a pattern this block takes over.

## Definition of done

1. **An AI block `pipeline-manager`** (`[ai] pipeline_manager_model`, Opus by default; pool 1; its own
   `pipeline_manager_session_usd` cap; within the daily cap) run like the other sessions: in a container on a
   read-only clone of main, its conversation kept as a `session` item related to what it worked on, its brief carrying
   the knowledge. It takes one `situation/*` item at a time (a new kind: raised, handled, failed). It runs while the
   switch `managing-open` reads 1 (`[manager] open` in the settings, 1 by default; 0 in `factory.local.toml` pauses it).
2. **Triggers** (`dev/bin/watch.py`, the program block `pipeline-watch`, every 5 minutes), in this order, one raised at
   a time and none while another is raised or leased:
   - the queue blocked (`run/queue.json` `blocked`, or an open intervention of class `queue`);
   - a gap dead for a while, or parked recently (`[manager] parked_within_hours`), unless another gap carries its
     branch on already;
   - a gap in one working or waiting state longer than its threshold (`[manager.stuck_hours]`, per state): its time
     there summed over visits from `time_in` when state-times is on main, else from its own moves (lease bounces are
     not a new visit); not when the wait is explained (its pool full, its dependencies unmerged, a push held);
   - an open intervention not the manager's own, unremedied past `[manager] intervention_hours`;
   - a heartbeat every `[manager] heartbeat_minutes` (30), only when the pipeline changed since the last.
   Deduplicated: each situation carries a fingerprint (its subject and the visit, park or change it is about); one with
   a fingerprint already raised is never raised again.
3. **The brief** (`dev/bin/manager.py`), assembled by the program: the situation and its subject (the gap's history,
   park or dead reason, reviews, findings, sessions, the tails of its suite and queue logs), main's recent commits,
   the queue's state, the open interventions, the known flakes, the pipeline by state, the velocity readings, and the
   knowledge entries (`knowledge.block`).
4. **Tools: `dev/bin/manage.py`**, a small CLI. The session answers with the calls as argument lists in a fenced JSON
   block; the program runs each through the same parser (the coordinator may run it by hand). Allowed directly:
   - `continue GAP [--depends-on a,b]`: a new gap that `continues` a parked (or dead) branch, refused while another gap
     holds it;
   - `reapprove GAP --why`: only when its last failure was environmental, verified by the program, never taken from
     the AI: the failed tests (the queue's, or the fast suites' in the container) run again on main, in the same
     environment, and must fail there too. A queue failure goes back to approved (`gap.retried`), a fast-suite failure
     to built (`gap.built`, its head unchanged); refused when the branch moved since, or no test is named;
   - `flake TEST --why`: the test recorded as a flake;
   - `file-gap --title T --definition-text D [--depends-on ...]`: written to `run/defs/` and requested;
   - `remedy INTERVENTION --why`: an open one marked remedied; a queue one only once the checkout's main is clean and
     not ahead of the remote's.
   Every action records an `intervention.recorded` with a class and `by: pipeline-manager`, so the interventions (and
   any risk measure on them) still count factory defects; the watch never raises the manager's own.
5. **Gated** (asked as actions held in the inbox for the coordinator): `close GAP` (a new state, `closed`), `park GAP`,
   `pool ROLE N`, and `change --what` for anything else: dev/model, the factory's settings, or anything that pushes
   or touches origin. Each is also recorded as an intervention.
6. **The velocity watch**: on each heartbeat the program reads queue wait, suite minutes, cycle hours and each waiting
   state's time; when the queue's goal (`queue-wait-short`, `suites-in-time`) is off it files a gap proposing the
   improvement (merge batching with bisection for the wait, faster suites for the minutes), at most one open at a time
   and never one whose branch exists.
7. **The model** (`dev/model/manager.yaml`): the kind, the switch, the watch and the block, the stock of situations
   with its goal, the auxiliary `stuck-gaps` held at 0 (a goal), the gated actions, and the manager's sessions in the
   AI spend.

## Acceptance tests

`tests/test_factory_manager.py`, with the stand-in AI:

- each trigger (queue blocked, dead, parked, stuck from moves and from `time_in`, intervention, heartbeat), and
  deduplication (the same situation twice raises one; one at a time);
- `continue`, `reapprove` (refused when the tests pass on main; a queue failure to approved and a fast-suite failure to
  built when they fail there too), `flake`, `file-gap`, `remedy` (a queue one refused while main is ahead);
- the gated actions held, and their commands once approved;
- every action records an intervention with its class and `by`;
- a whole run: the brief carries the situation and the knowledge, the stand-in's calls are run, the situation handled;
- the velocity watch files one gap when the queue wait is off, and none while one is open.

## Size budget

450 net lines of the programs in `dev/bin/` (the model, the prompt, tests and docs apart).
