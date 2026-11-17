# The job: a senior engineer's and SRE's work

This is one person's job, written down as conditions that are true or false right now, and run.
Reviews asked of me, my own PRs, chat that mentions me, pages, outages and their postmortem
actions, flag ramps waiting for my approval, secrets nearing expiry, the CI server falling
behind, customer tickets, documents moving toward the change advisory board, teammates' stale
PRs, the weekly update. Each is an item that moves through states, each domain is a system,
and each responsibility is a goal.

It follows the shape of the job (five verbs):

| Verb | Who does it here |
|---|---|
| **Watch** | programs: the watchers (`bin/watch.py`), filtering what each work system says into items |
| **Prepare** | preparers (`bin/prepare.py`): a draft in `outbox/` for every item that arrives |
| **Decide** | me: the person blocks ask, and I approve, reject, declare, choose |
| **Perform** | me: I answer, present, persuade, run the command, command the incident |
| **Record** | programs: the morning brief and the ledger (`bin/rhythm.py`), files in `outbox/` |

The system's first jobs are to watch everything so I don't have to, prepare me before I decide
or perform, and record everything so the evidence builds itself.

## It never writes to work systems

Every part of it is read-only toward the outside, so it can run on a work laptop:

- the watchers only read (the simulated world here; with `JOB_GH=1`, GitHub through read-only
  `gh` commands, see below);
- the preparers only write Markdown into the local `outbox/` folder, and record in ergostat that an
  item was prepared. Nothing is posted, commented, filed, approved, merged, sent or run;
- what is mine (the charter's "never without me": running anything against production or a
  customer's system, approving, declaring an incident, speaking as me, the conclusions of a
  review or a postmortem) is a **person block** (`type: person`, agent `me`). It asks me when
  its goal is off (`person.asked`, in the Record page and `ergostat event`), and does nothing
  itself. I act in the work systems by hand; the watchers see it.

## Run it

It needs no accounts and nothing installed beyond ergostat: the job's world is simulated
(`world/`), and the preparers are stand-ins. Work on a copy, since it writes `run/` and `outbox/`:

```bash
cp -r examples/the-job /tmp/the-job && cd /tmp/the-job
ergostat run                       # prints the page's address
ergostat loop                      # every goal: holding or off
ergostat item --kind review        # the reviews asked of me, by state
ls outbox/                         # the drafts, the morning briefs and the ledger
ergostat run --stop
```

A working day lasts a minute (`JOB_DAY=60`, in seconds; `JOB_DAY=300 ergostat run` for a slower
week), so five minutes is a working week: Monday starts with things already waiting, two of them
for too long, and Tuesday morning has an outage. To start over: stop it, `ergostat reset --yes`
and `rm -rf run outbox`.

## Where to look

- **Diagram, Dynamics** (the stock-and-flow view): `job` open, each domain a closed module
  with the number of feedback loops inside, and the influences between domains (an unreviewed
  flag ramp raising alerts). The side panel says what needs attention: the goals that are off.
  **Open** a domain to see its stocks, flows and loops in place (R and B mark the reinforcing
  and balancing loops), or go **Into** it to draw it alone.
- **Diagram, Blocks** (the control view): open a domain to see each goal's loop as a block
  diagram: the setpoint, the switch that acts while the goal is off, the block it commands (a
  preparer, program or AI, or me, a person), and the measured stocks it moves.
- **Loops**: every goal, holding or off, how often it is off and how fast it comes back.
- **Items**: every kind, each item's state and fields, and how long it spent in each state. An
  item's page shows its draft (`brief`, `nudge`, `reply`, `comment`, `ticket`, `plan`,
  `explanation`, `draft`) rendered. `day/<date>` (the simulated week starts on this week's Monday) shows that day's **morning brief** and its
  **ledger**.
- **`outbox/`**: the same files, for an editor: `review-2041.md`, `alert-703.md`,
  `brief-<date>.md`, `ledger-<date>.md`, ...

## What it models

Each domain is a system within `job` (the files in `job/`), and every one has the same shape: a
watcher brings items in, a preparer prepares each, and I do what is mine.

| Domain | Items | Watched | Prepared (block, rung) | Mine (person block) |
|---|---|---|---|---|
| delivery | `pr/1181` waiting → stale → nudged → reviewed → merged | my PRs on the code host | a nudge for a PR waiting a day for a first review (`nudge-drafter`, ai) | `chase-reviewers`: send it, or ask in person |
| stewardship | `review/2041` requested → briefed → answered | reviews asked of me | a brief: what it does, its risk, what to look for, related commits (`review-pre-reader`, ai) | `write-reviews`: the verdict and the tone |
| documents | `doc/12-proposal` needed → drafted → approved | each change's paper trail | the next document from my notes: problem statement, proposal, design, board ticket (`doc-drafter`, ai) | `persuade`: the thinking; reviewers and the board |
| awareness | `mention/88` new → triaged → answered; `secret/tls-cert-api` expiring → drafted → rotated | chat, filtered to mentions (and digested); the secrets store | a triage and a reply (`mention-triager`, program); a rotation ticket (`rotation-ticket-drafter`, program) | `answer-mentions`: speaking as me |
| incidents | `alert/703` fired → drafted → commented; `outage/41` suspected → declared or dismissed → resolved → reviewed (its postmortem); `action/902` open → planned → done | the pager; the tracker's postmortem actions | a usefulness comment, what changed before it, who is on call (`alert-companion`, ai); a plan for each action (`action-planner`, ai) | `post-alert-comments`; `declare-incident` |
| safety | `ramp/301` pending → briefed → approved, rejected or went-ahead → broke or proved-fine; `ci/2.41` released → planned → upgraded | the flag system; the CI server's releases | a ramp research brief (`ramp-researcher`, ai); an upgrade plan (`upgrade-planner`, program) | `approve-ramps`: my name is on it |
| support | `ticket/5201` new → explained → answered | customer tickets assigned to me | what the command it asks for does, checked against the ticket (`command-explainer`, ai) | `run-commands`: whether it runs, and I run it |
| team | `team-pr/3104` stale → nudged → moving; `update/2026-11-16` due → drafted → sent | teammates' PRs, reported once stale 3 days; the calendar | a nudge (`team-nudge-drafter`, program); the weekly update from the ledger (`update-drafter`, ai) | |
| rhythm | `day/2026-11-16` started → briefed → ended → recorded | the working day's clock | the morning brief (`brief-builder`, program); the ledger (`ledger-keeper`, program) | |

**Stocks** are counted from the items (no sensor program): the reviews waiting for a brief,
the alerts with a comment drafted and not posted, the secrets within 30 days of expiry with no
ticket, my PRs stale without a nudge. **Flows** are the items moving between those states,
counted as they move; each domain's arrivals are measured by its watcher, which is a sensor:
it measures, and never acts. **Auxiliaries** count what has waited too long (`reviews-late`:
requested over a working day ago and not answered), a function of the waiting items and the
clock.

**Goals** are the charter's conditions (§4), each held at zero:

| Goal | Condition |
|---|---|
| `stale-prs-nudged` | no PR of mine has waited over a working day for a first review without a nudge drafted |
| `my-prs-reviewed` | no PR of mine waits over 2 working days for a first review |
| `every-review-briefed`, `reviews-on-time` | every review requested of me has a brief, and is answered within 1 working day |
| `every-doc-drafted`, `board-before-rollout` | the next document of each change is drafted; every change is approved by the board before its rollout (critical) |
| `every-mention-triaged`, `mentions-answered` | every message mentioning me is triaged, and answered within 4 hours |
| `secrets-ticketed` | no secret I own expires within 30 days without a ticket (critical) |
| `every-alert-drafted`, `alerts-commented` | every alert has a drafted usefulness comment, and my comment within half a day |
| `outages-decided` | every suspected outage is declared or dismissed, by me (critical) |
| `actions-planned` | every postmortem action of mine has an owner, a date and a first step |
| `every-ramp-briefed`, `ramps-decided` | every pending flag ramp has a research brief; none waits over a day for my decision |
| `ci-upgrade-planned` | the CI server is within one version of current, or an upgrade plan exists |
| `every-ticket-explained`, `tickets-within-sla` | every customer ticket's command is explained; every ticket has a response within its SLA (critical) |
| `team-prs-nudged`, `update-drafted` | no teammate PR is stale 3 days without a nudge drafted; the weekly update is drafted by Thursday |
| `morning-brief-ready`, `day-recorded` | today's brief is written; every working day is in the ledger |

The goals that are off are my to-do list, built for me: the morning brief ranks them first.

## The loops

Each domain has two balancing loops, one inside the other:

- **the preparation loop**, fast: an item arrives, the goal "every X is prepared" goes off, its
  preparer runs while it is off, the item moves to prepared, and the goal holds again. Seconds.
- **my loop**, slow: an item waits too long, the goal "every X is done in time" goes off, and the
  person block asks me. It closes the long way, through the prepared stock: what I do drains it,
  and the count of late items follows the stock down (`ergostat explain reviews-on-time`).

Preparing is what makes my loop fast: in the simulation (`world/me.py`) I act within hours on
what has a draft, and a day or two late on what has none. During an outage I am three times
slower at everything else, so on Tuesday the late reviews, mentions and alert comments pile up,
their goals go off, and they come back once the incident is resolved.

Between the domains, influences (dashed, `driven-by`): a flag ramp I did not decide in time goes
ahead without me (`ramps-went-ahead`, driven by `ramps-late`) into a stock, `unreviewed-ramps-live`:
live in production, unreviewed. Each one there may break its service hours later (`ramps-broke`,
an outage begins) or prove fine after half a working day (`ramps-proved-fine`). Alerts
(`alerts-fired`) and the outages the pager notices (`outages-noticed`) follow that stock, not the
rate ramps went ahead at: in system dynamics a connector acts at once, so a cause that acts over
time goes through a stock, and the stock is the delay (`docs/MODELLING.md` in ergostat). A declared
outage waits for its postmortem (`outages-to-review`); each postmortem (`postmortems`) leaves two or
three actions, filed as it ends (`actions-filed`, driven by `postmortems` at once, `instant: true`,
and by `actions-per-postmortem`, the ratio). In documents, each approval opens the change's next
document at once (`paper-trail`, the one reinforcing loop), until the board approves it.

## The numbers

Where the world's code makes a rate known, the model writes it as an equation (docs/SPEC.md §7b),
in the world's own terms. A ramp that goes ahead unreviewed breaks its service at 45% a tenth to
half a working day later, or is called fine after exactly half a day: two material delays of the
ramps that went ahead (`DELAY3(break-share * flow.ramps-went-ahead, time-to-break /
workdays-per-hour)`), whose stages together are the ramps live unreviewed. A ramp that breaks starts
one outage, so outages are a coflow of the breaks (`workdays-per-hour * outages-base +
outages-per-break * flow.ramps-broke`), and every outage pages three to five times, so alerts are a
coflow of the outages (`workdays-per-hour * alerts-base + alerts-per-outage *
flow.outages-noticed`). The values come from `world/traffic.py`; those marked `estimate: true` are
fitted from the record. The watchers count arrivals over the last ten minutes (`averages: 10m` on
their sensors), and the model's rates are read through the same ten minutes before they are
compared. The Fit page shows how well each equation and each stock follows the record, and
**Estimate now** proposes a value only when the record supports it (enough of it for the slowest
time constant the value touches, more than two standard errors from the value written, and better
on the last fifth held out): nothing changes until you accept one.

## The code host for real (optional, read only)

With `JOB_GH=1`, my own open PRs and the reviews requested of me come from GitHub, read with my
own `gh` sign-in (`gh auth login`, once), instead of the simulation:

```bash
JOB_GH=1 ergostat run
```

`bin/codehost.py` runs only `gh search prs` and `gh pr view` and refuses any other `gh` command;
it polls every two minutes (`JOB_GH_EVERY`), and a working day there is a real day
(`JOB_GH_DAY=86400`): a review is late a day after it was first seen. The briefs and nudges for
those PRs are drafted from `gh pr view` (files, size, reviewers). Nothing is ever posted,
commented, approved or merged: I write my reviews on GitHub myself, and the watcher sees them.
Everything else (chat, the pager, flags, secrets, tickets, documents) stays simulated. It is off
by default.

## What is real and what stands in

- **The world** (`world/`) is simulated: teammates, chat channels, production, the pager, the
  flag system, the secrets store, the CI server, customers, the doc index, the board, and me.
  It is a function of the clock: whoever reads it first (a watcher) moves it on to now. It keeps
  its state in `run/world/` and a feed of what happened, which the watchers read the way they
  would read a work system's API.
- **The watchers** are programs and stay programs: filtering is cheap and needs no model.
- **The preparers** of rung `ai` are stand-ins: programs that fill the sections an AI agent
  would be asked for (their prompts are in `prompts/`). Making one real means giving its block a
  model, which waits on the compliance boundary (which models may see which data); until then,
  the ones of rung `program` already do their whole job without one.
- **Me** (`world/me.py`) stands in for the owner. On your laptop, with `JOB_GH=1`, the code
  host's part of me is you.
