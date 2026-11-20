# Adding a small control system

Most of what someone wants kept going at work is small: *watch for X and respond*, *remind them until they
answer*, *report every morning*, *keep Y under a limit*, *when a ticket of type Z arrives, do these steps*. Each is a
small control system: something that measures (a collector of events, a sensor), a model of what accumulates (a
stock and its flows), a goal, and an actuator that does the work (a block). ergostat has each of these shapes
ready as a **template**: one `uses:` entry, a few parameters, and it is in the model, drawn, checked and running.

The usual way is to ask an AI agent in plain words, with ergostat's authoring skill; it picks the shape, writes the
entry and any scripts, tries it on a copy, and shows you the diagram and the diff before turning it on. You can
also write the entry yourself.

## Ask an agent

Once, in the project:

```bash
claude mcp add ergostat -- ergostat -C /path/to/project mcp        # ergostat's tools, for Claude Code
mkdir -p .claude/skills && cp -r ~/ergostat/docs/skills/ergostat-author .claude/skills/   # the skill
```

(`~/.claude/skills/` instead makes the skill available in every project.) Then ask for what you want, the way you
would ask a colleague: "when someone asks me for a review, remind them every day until they answer, three times at
most". The skill (`docs/skills/ergostat-author/SKILL.md`) has the agent:

1. pick the shape (or several), and ask you only what has no safe default (a real source it cannot reach, a limit
   you did not say);
2. write the `uses:` entry, and scripts where the template runs a command (`scaffold` starts each one, runnable as
   it is; they may live in a private folder outside any repository);
3. check it (`add_use` shows the diff and what `check` says, writing nothing) and try it on a scratch copy
   (`try_use`: half a minute with a record of its own, then what moved and what failed);
4. show you the diff and where it is drawn (`where_drawn`), and write it only when you say so.

Writing it is your own change to the model, made on your behalf: the running ergostat picks it up. It is not a
proposal for the judge (that is the modelling subsystem's, which alone changes a running model of its own accord).

## The shapes

| Template | Use it for | Its goal | Leave out, and it runs on |
|---|---|---|---|
| `respond-to` | items arriving that each want an answer within a time | the oldest unanswered item's age, under `within` | a made-up feed; a pretend answer |
| `re-ping` | something you asked of someone, reminded until they answer | no question a period without a reminder; at `limit`, a person takes over | a feed whose questions are answered after a while; a reminder that sends nothing |
| `daily-report` | a report on a schedule | every scheduled report written | a summary of the model now |
| `keep-under` | a measured level held under a limit | the level under `limit` | a level that creeps up; a correction that takes a tenth off |
| `steps` | a kind of item worked through steps in order, by programs or AI agents | nothing waits at a step; nothing stays stuck | a made-up feed; steps that do nothing |
| `collect` | recording what a command or an API says, as items | (an instrument: none) | a made-up feed |
| `modelling` | the model itself, improved as a loop of its own (every model should have one) | the model's replay off the record by at most `fit` | an improver that proposes nothing of its own and asks ergostat's finders to look again |

Every template runs on its free stand-ins until you give it the real thing, so it can be seen and tried before any
access exists; `check` says which instances still do (`template-stand-in`). `ergostat help adding` is this page;
the MCP tool `templates` lists every template with its parameters, and with `name` gives one's parameters,
reading and example. The format is `docs/SPEC.md` §2a.

### respond-to

```yaml
uses:
  help-queue:
    use: respond-to
    with:
      within: 4h                          # the commitment
      command: ./bin/help-queue.sh        # prints the open questions as JSON, each with an id
      answer: ./bin/draft-answer.py       # given each one on standard input; exit 0 when answered
      pool: 2                             # at most two answered at once
```

- **Control:** two balancing loops on the age of the oldest unanswered item. The fast one (`picked-up`) is an
  on-off controller with its setpoint at `act-after` (0: at once): its actuator, `answer`, takes the waiting
  items, the longest waiting first, each leased to a run of its own (SPEC §9.5) that runs the `answer` command on
  it, `pool` at once. An answer that fails gives its item back to be taken again; after `tries` it is a dead
  letter, still unanswered. The slow one (`on-time`) is the commitment, `within`; while it is off, a person is
  asked (`escalate`). Preparing fast keeps the slow loop quiet.
- **System dynamics:** a stock of items unanswered (waiting, being answered, or given up on), filled by the
  arrivals (a disturbance: nothing in the model sets them) and drained by the answers; the oldest item's age,
  counted from its arrival whoever holds it, is an auxiliary of the stock and the clock.

### re-ping

```yaml
uses:
  review-reminders:
    use: re-ping
    within: delivery
    with:
      every: 1d
      limit: 3
      command: python3 bin/my-asks.py     # what I asked and am waiting on; an answered one says "event": "answered"
      ping: python3 bin/remind.py         # writes one reminder (as a draft, unless sending was approved)
```

- **Control:** an on-off controller on the oldest unanswered question's age, its setpoint one period. While it is
  off, the pinger reminds each question whose last reminder is a period old. The count limit is saturation, with
  an escalation ladder: past `limit` the actuator stops acting on that question and hands it to a person (`take-over`),
  held by a second goal, that nothing given up waits.
- **System dynamics:** a stock of questions unanswered, drained by answers (which the source reports) and by giving
  up, into a stock a person clears; the reminders sent are a running total.

### daily-report

```yaml
uses:
  morning:
    use: daily-report
    with:
      cron: "30 8 * * 1-5"                # 08:30 on working days, local time
      render: ./bin/morning.sh            # prints the report as Markdown (left out: a summary of the model now)
```

- **Control:** an on-off loop on the reports due, setpoint 0. It is feedback, not a timer: a report missed while the
  machine slept is written as soon as it is back, and one already written is never written twice.
- **System dynamics:** a stock of reports due, filled by the clock (each scheduled time passing, the disturbance)
  and drained as each is written into a running total. Each report is an item, `morning/2026-11-18`, its file
  shown rendered on its page.

### keep-under

```yaml
uses:
  build-cache:
    use: keep-under
    with:
      unit: GB
      limit: 20
      until: "<= 15"                      # where the correction stops: the deadband
      measure: du -sk ~/.cache/build | awk '{print $1/1048576}'
      act: python3 bin/prune-cache.py     # one step of the correction; prints {"moved": <GB freed>}
```

- **Control:** an on-off controller with hysteresis: off past `limit` (plus `tolerance`), the correction runs while
  it is off and stops at `until`. The gap is the deadband that keeps it from chattering; `max` bounds one run's move
  (saturation). `rung: person` asks a person instead of running a command.
- **System dynamics:** one stock, the level, filled by whatever raises it (measured from its own rises: the
  disturbance) and drained by the correction: a first-order balancing loop.

### steps

```yaml
uses:
  regressions:
    use: steps
    with:
      url: https://tracker.example.internal/api/issues?type=regression
      headers: ["Authorization: Bearer $TRACKER_TOKEN"]
      pool: 2                                   # at most two items at each step at once
      tries: 3                                  # attempts at a step before an item is a dead letter
      workspace: {repo: ../product, size: 2}    # a worktree per item, for the AI agent steps
      actions:                                  # what an AI agent step may ask for, gated
        - name: push
          run: git push origin HEAD:refs/heads/{branch}
          gate: approve                         # held until you approve it
      steps:
        - name: label
          run: python3 bin/label.py             # a program step
        - name: find-culprit
          run: python3 bin/find-culprit.py
        - name: draft-revert                    # an AI agent step
          prompt: prompts/draft-revert.md
          tools: [Read, Edit, Bash]
          actions: [push]
```

- **System dynamics:** an aging chain (Sterman, ch. 12) with work in progress at every step: the items waiting at
  a step, taken into the items it is working on, and passed to the next step's queue (the last into a running
  total done). An item given back flows from the work at its step to its queue again (rework); one that fails every
  try leaves the chain for a stock set aside.
- **Control:** one balancing loop a step, each an on-off controller holding its queue at 0, its actuator that
  step's block. The block **takes** the items at its state: ergostat leases each to a run of its own (SPEC §9.5),
  `pool` at once, the oldest first, as soon as it arrives. The run moves its item on (the lease's ack) or gives it
  back (a nack, its attempt counted); a run that goes silent past its lease's TTL loses the item, and it is taken
  again. After `tries` attempts at one step the item is a dead letter and a person is asked (`unstick`): fix the
  cause, then `ergostat lease ITEM --redrive` gives it another go. Add a step to the list and its stocks, flows,
  goal and block follow.
- **A program step** (`run:`) is given its item on standard input; exit 0 moves it on, anything else gives it back.
  Its lease's TTL is the program tier's (5 minutes, or `timeout` when longer) unless `ttl` says.
- **An AI agent step** (`prompt:`, a file or the text; `model`, `tools`) is a Claude Code session on its item. It
  moves the item on by saying `{"event": "KIND.STEP-done"}` (the prompt should tell it so: `regressions.draft-revert-done`
  here), or gives it back with `{"nack": "why"}`. Its lease's TTL is the AI tier's (40 minutes) unless `ai-ttl`
  says; it may run for `ai-timeout` (30m). With `workspace`, each item has a git worktree of its own, on its own
  branch, kept across its steps, attempts and review, and cleaned once it is done (SPEC §12k). With `actions`, the
  steps that name them may ask for those outward acts, each run only as its `gate` says (`approve`: held for you;
  `auto`; `deny`), and a step with `tools:` or `actions:` runs in the sandbox.

### collect

```yaml
uses:
  deploys:
    use: collect
    with:
      url: https://ci.example.internal/api/deploys?since={cursor}
      headers: ["Authorization: Bearer $CI_TOKEN"]     # secrets stay in the environment
      cursor-field: finished_at                         # only what is past the latest seen
      fields: [service, version, finished_at, status]
      poll: 5m
```

- **Control:** an instrument, not a controller: the sensor on an arrival flow. Each record it has not seen (by id,
  and by event when a record names one) is recorded once, as an event about the item `KIND/<id>`; the number it
  reads is the new items per hour. It never acts on what it reads.
- **System dynamics:** the inflow of whatever the source holds, into its own running total, or into a stock of
  yours (`into:`) that something else drains. `respond-to`, `re-ping` and `steps` each have one inside.

### modelling

```yaml
uses:
  modelling:
    use: modelling                        # every model: one line, and the model improves as a loop of its own
    with:                                 # all optional
      fit: 0.05                           # the most scaled error the replay may have (the goal model-fits)
      prompt: prompts/improver.md         # the improver's prompt (else ergostat's own, which reviews any model)
      run: ""                             # give it to claude -p (else the free stand-in); or a wrapper of your own
      rules: true                         # the rule tier (default on, free): mechanical fixes for what check finds
      ai: true                            # the AI tier (default off): what the rules cannot answer, on ai-model
      ai-model: haiku                     # (default haiku); ai-every 10m, ai-most 8 requests a call
      redesign: {when: auto, model: haiku, budget: 0.5, rounds: 3, daily: 2}   # with ai: true, the redesigner (auto|ask|off)
      review: {when: auto, model: haiku, kinds: structure redesign, most: 3}  # with ai: true, the reviewer (auto|off)
      accept:
        parameter: auto                   # a value the judge passes is written at once (else the owner accepts each)
        description: auto                 # and so on for unit, equation, rename, structure (a rewired chain or a
        unit: auto                        # removal always waits for the owner)
```

- **Requests and tiers:** everything `check` finds (findings, a kind's chain, the craft notes, the coherence
  mismatches once there is record) is a request (`ergostat.modelling-request`), raised by the collector on
  `requests-raised` (every `requests-every`, 2m) and counted while unanswered (`unanswered-requests`, held at 0 by
  the goal `requests-handled`). The `fixer` block (the rule tier, every `rules-every`, 1m) proposes the changes a rule makes
  safely and certainly; the `modeller` block (with `ai: true`) proposes the rest, given each request with the model
  near it. Both propose ordinary changes; the judge decides by class (SPEC §12e).
- **Redesign:** with `ai: true`, the `redesigner` block reviews the structure on its own (`when: auto`), a system at a
  time: when its replay is worse than its mean, a finding says the structure is wrong, refinement stalled, on the
  first run and once a day; or when the owner asks (`ergostat improve --redesign [SYSTEM]`, the Model page's Redesign
  button). It proposes one change set (renames, rewiring, removals, equations, descriptions), worked a few `rounds` on
  a scratch copy within `budget` dollars a run and `daily` dollars a day, judged as a whole by a scorecard. **It is
  never written without the owner's approval** (the review queue and the inbox) unless `accept: {redesign: auto}`, and
  even then not one that takes a part away, rewires a chain or changes control.
- **Review:** with `ai: true`, the `reviewer` block reads each change of `review.kinds` (structure and redesign; add
  `equation` if you like) after the judge passes it, as a deliberately disagreeable senior modeller, through the review
  checklists of `docs/MODELLING-WELL.md` (the causal story, units and boundary, fitting noise, one coherent change, the
  behaviour it predicts). It passes it, sends it back to its author with its findings (`revise`: the author's next
  proposal on those parts is the second round, and a second revise is a reject), or rejects it (the change fails, and
  the memory holds it back). Those kinds are written by the policy, and offered in the inbox, only after its pass; the
  owner may still accept one from the review queue. Each author's prompt carries the reviewer's recent verdicts on its
  own changes. Its calls count against `redesign.daily`, the template's one daily cap; `ergostat measure` says its
  passes, revises, rejects and misses (`ergostat.model.reviews-*`, `review-misses`).

- **Control:** one balancing loop that closes the long way (SPEC §12e). The goal `model-fits` holds `model-error`
  (ergostat's measure `ergostat.model.fit`, the Fit page's total) at or under `fit`; while it is off the
  `improver` runs (`rung`: an `ai` block by default, or a `program`, or a `person` asked) and proposes changes with
  their evidence; the `judge` (a built-in block) replays each on the record after it, in several windows, and
  writes what `accept` allows: nothing by default, the owner accepts in the Fit page's review queue. Its schedule
  and verdicts are `judge-every`, `hold-out`, `windows`, `threshold` and `warm-up` (the judge's own defaults when
  left out); the improver's `every` (3m) and `timeout` (15m); `sessions: true` keeps each improver run as a
  `session` item, for an improver that reports `session.ran`.
- **System dynamics:** `model-error` drained by what the changes written took off it (`model-mended`, each
  change's `fit_gained`) and moved either way by the rest (`model-drift`: the record moving on, the world drifting); the changes to the model (items of ergostat's kind `ergostat.model-change`, whoever
  made them) an aging chain by state: `pending-changes` (checked) → `changes-testing` → `passed-changes` →
  `accepted-changes` (a running total), leaving as superseded or failed.
- **Once a model, names as written:** unlike the other templates, its parts are not prefixed: they are
  `model-error`, `pending-changes`, `changes-testing`, `passed-changes`, `accepted-changes`, the flows
  `model-drift`, `model-mended`, `changes-made`, `changes-superseded`, `tests-started`, `changes-passed`,
  `changes-failed`, `changes-accepted`, `unanswered-requests`, `answered-requests`, `requests-raised`,
  `requests-answered`, `changes-made-by-fixer`, `changes-made-by-modeller`, the goals `model-fits` and
  `requests-handled`, and the blocks `improver` (or `improver-by-hand`), `fixer`, `modeller` and `judge`, in a system named for the instance (`modelling`). A system the model declares under that name (to give
  it `show:` or `within:`) is the model's. `check` notes a model without it (`no-modelling-loop`).

## From a described workflow to a model

A workflow described in words ("a feature-flag ramp request is researched, approved, ramped in stages and
confirmed") is one item kind moving through states, and its model is **one chain**: a stock per state that waits, and
a flow from each state's stock into the next one's, never an outflow to a cloud. The method, in order:

1. the item kind and its states, in order (`items:`, `states:`, `on:`);
2. one stock per state that waits, counted by an `items:` sensor (`state: S`): a count, never `measure: oldest`;
3. one flow per move, from the state's stock to the next one's, measured from the item moves (`entering: NEXT`);
   arrivals in from outside at the start, completions out at the end;
4. a collector that finds the work (`collect`, `into:` the first stock, or the source's sensor) feeding the first
   stock;
5. one block per step that does the work: `takes: {kind, at, to}`, with `pool` and `lease`, and `goal:` the goal on
   the stock it drains;
6. goals on what matters: nothing waiting at a state, or the age of its oldest item (a stock of its own beside the
   chain, `measure: oldest`, with no flows), throughput, dead letters;
7. gated actions (`gate: approve`) for every outward act;
8. `ergostat check`, and every structure finding fixed: `outflow-not-chained` (an outflow to a cloud whose items go
   on to the next state's stock: `to:` it), `state-stock-without-inflow`, `move-without-flow`,
   `state-stocks-disconnected` and `loops-not-connected`, each with the edit that fixes it. Then look at both
   diagrams (`/diagram?view=dynamics` and `view=blocks`): one connected chain per kind, arrivals in at the start,
   completions out at the end, each step's loop sharing the chain's stocks, and no stock without an inflow unless
   things come from it;
9. last, **reconcile the three views**: run it (a minute on its stand-ins, `try_use`, or the live record), then
   `ergostat check` again (or the MCP `coherence` tool). Its Coherence section holds what the items really did (the
   Process view) against the chain (Dynamics) and what moves the work (Blocks): a score per kind, and each mismatch
   with its file, line and fix. Fix the model, or the blocks, until every kind agrees (`N of N agree`); a kind that
   needs more record has not run long enough. A move the record shows and no flow carries is a missing flow (rework
   needs one running back); a flow no block moves needs its block, or an external one; a block seen moving what it
   does not declare needs its `takes:` or `out:`; a block with work that something else moved on is not recording its
   own events, or is the wrong mover. `docs/MODELLING.md` explains each.

When every state is a step a block works on, `steps` is this method in one entry. Written by hand,
`examples/ticket-factory` is the worked example (its `ticket.yaml`, `factory/intake.yaml` and `steps/*.yaml`; the
skill quotes them).

**Why no `workflow` template.** A kind and an ordered list of states, chained, with a sensor per stock and a slot per
step for a block, is what `steps` already makes: its states are the step list, each step's stock flows through the
items it is working on into the next step's, the collector feeds the first and the last fills a running total. A
second template that differs only in naming the states for outcomes rather than steps would be two names for one
shape; and where a workflow does not fit `steps` (a person or the outside moves the item, a step branches or sends
back), a template would hide exactly the parts that need writing by hand. The check, not a template, is what keeps a
hand-written chain whole.

## A worked example

The request: *"When I ask someone for a review and they haven't answered within a day, remind them. Three times at
most, then hand it back to me."* In a copy of `examples/the-job`:

1. The shape is `re-ping`. Nothing needs asking: the period (a day) and the limit (three) are in the request, the
   source (the reviews I asked for) is a script to write, and the reminder is a draft, never sent.
2. `scaffold` with role `source` and path `bin/my-asks.py` writes a script that runs as it is and prints a
   stand-in record; its TODO is where `gh search prs --author @me --review-requested ...` would go, read only.
3. `add_use` (instance `review-reminders`, template `re-ping`, file `job/review-reminders.yaml`, within
   `delivery`) writes nothing yet; it shows the diff:

   ```diff
   +uses:
   +  review-reminders:
   +    use: re-ping
   +    within: delivery
   +    with:
   +      every: 1d
   +      limit: 3
   +      command: python3 bin/my-asks.py
   ```

   and that it checks, with one finding: `use review-reminders: runs on free stand-ins (ping: a pretend reminder,
   nothing sent)`. Its parts: the stocks `review-reminders-unanswered`, `-given-up` and `-pings-sent`, the goals
   `review-reminders-reminded` (`oldest <= 24` hours) and `-none-given-up`, the blocks `-pinger` (program) and
   `-take-over` (person). `job/*.yaml` is already included, so the main file is unchanged.
4. `try_use` with `every: 20s`, `limit: 2` and `poll: 10s` (a day shows nothing in half a minute) runs a copy:

   ```
   items review-reminders: 1 waiting
   block review-reminders-pinger ran 1 times, moved {'review-reminders-pinging': 1.0, 'review-reminders-giving-up': 0.0}
   goal review-reminders-reminded (<= 0.005555556): holding
   goal review-reminders-none-given-up (<= 0): holding
   ```

5. `where_drawn` gives the pages, `/diagram?view=dynamics&system=review-reminders` (its stocks and flows inside
   `delivery`) and `view=blocks` (its two loops as block diagrams), and the system drawn as text. The agent shows
   these and the diff, says what still stands in (the reminder), and asks. On yes: `add_use` with `write: true`.

## Your own templates

A template is a YAML file (`docs/SPEC.md` §2a says how to write one: `${param}`, `if:`, `each:`). Keep yours in a
folder of your own, outside any repository if you like, and name it in the main file:

```yaml
library:
  - ~/work-templates
```

(or `$ERGOSTAT_LIBRARY`, folders separated by `:`). They are listed beside ergostat's own; one with the same name
as one of ergostat's is used in its place, and `check` says so. A template may use templates (its own `uses:`), and
may keep its scripts beside it (`${here}/fetch.py`).
