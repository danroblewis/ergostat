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
| `steps` | a kind of item worked through steps in order | nothing waits at a step; nothing stays stuck | a made-up feed; steps that do nothing |
| `collect` | recording what a command or an API says, as items | (an instrument: none) | a made-up feed |

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
```

- **Control:** two balancing loops on the age of the oldest unanswered item. The fast one (`picked-up`) is an
  on-off controller with its setpoint at `act-after` (0: at once): its actuator, `answer`, runs the `answer`
  command on each waiting item, the longest waiting first. The slow one (`on-time`) is the commitment, `within`;
  while it is off, a person is asked (`escalate`). Preparing fast keeps the slow loop quiet.
- **System dynamics:** a stock of items waiting, filled by the arrivals (a disturbance: nothing in the model sets
  them) and drained by the answers; the oldest item's age is an auxiliary of the stock and the clock.

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
      steps:
        - name: label
          run: python3 bin/label.py
        - name: find-culprit
          run: python3 bin/find-culprit.py
        - name: draft-revert
          run: python3 bin/draft-revert.py
```

- **System dynamics:** an aging chain (Sterman, ch. 12): a stock for each step, each drained into the next by that
  step's flow, the last into a running total done; items that keep failing leave the chain for a stock set aside.
- **Control:** one balancing loop a step, each an on-off controller holding its stock at 0, its actuator that step's
  block: it runs the step's command on each item in its state and moves those that succeed on. Retries are bounded
  (`tries`), then the item is set aside and a person is asked (`unstick`). Add a step to the list and its stock,
  flow, goal and block follow.
- *Timer-driven, for now:* each step's block runs on its goal's clock and takes the items in turn. Item-driven
  dispatch with leases (an item handed to one run, taken back if the run goes silent) belongs to the engine; the
  steps will use it when it is there.

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
