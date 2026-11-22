# The ticket factory: a software engineer's ticket workflow, end to end

A Jira issue labelled for the factory is picked up, its repository found, the work done in a git worktree of its
own by an AI agent (Claude Code on haiku) or a free stand-in, a pull request opened with a description linking the
issue, a review asked for and re-pinged, the review answered with a commit, the SAIL label added on approval, CI
watched (and, when it fails, triaged, fixed and run again), the pull request merged, and the issue moved to Done. A
daily summary and an OKR are kept from the counts. It runs against real services (Jira Cloud, GitHub, a Prometheus
of its own), or offline against fakes.

It is a template: copy the folder, change `factory.conf` (and the gates in `factory/actions.yaml`), and point it at
your own Jira and repository. Every call to Jira is in `bin/jira.py`, every call to GitHub in `bin/github.py`, and
every write to either is a **gated action** of ergostat's (`factory/actions.yaml`): asked for by a step, held for
your approval or let through by its gate, and run by ergostat, never by the step.

ergostat knows no tickets: the ticket is this example's own unit of work, an item kind (`ticket.yaml`). What it uses
of ergostat's core:

- **leases and item-driven dispatch** (SPEC 9.5): each step's block `takes` the tickets in its state, a run per
  ticket, at most `pool` at once, each run holding a lease on its ticket;
- **workspace pools** (SPEC 12k): the work steps get the ticket's own git worktree from the pool `code`, on its own
  branch, kept through review and CI and cleaned when the ticket is done;
- **gated actions** (SPEC 12k), asked for by the steps' programs with `$ERGOSTAT_CMD act NAME --arg K=V`;
- **daemons** (SPEC 9.7, `docs/DAEMONS.md`): the short steps, the sensors and the teammate are long-lived processes
  handed each run or reading as a line of JSON, instead of a process each time (below, "Daemons").

## Setup

You need `uv`, `git`, `python3`, `gh` (signed in: `gh auth login`), `claude` (Claude Code, only for
`AI=claude`), ergostat (`uv tool install ...`, or run from ergostat's checkout: the scripts find it), a Jira
API token in a file (`~/.jira_token`: never printed, logged or recorded), and a repository to work in.

```bash
cp -r examples/ticket-factory ~/ticket-factory && cd ~/ticket-factory   # or work in place
./setup                  # writes factory.conf the first time: edit it, and run ./setup again
```

`./setup` checks the tools and the sign-ins (who the Jira token signs in as, the project and its statuses,
what `gh` can see), downloads Prometheus (`PROM_VERSION`, its checksum checked) into `SCRATCH`
(`~/.cache/ergostat-ticket-factory`, outside the folder), starts it on `PROM_PORT` (8797) and the exporter
on `EXPORTER_PORT` (8796), clones or fetches the repository into `run/repo` (the workspace pool's), checks the model,
starts ergostat with its page on `WEB_PORT` (8795), and prints what to open. `./setup --no-run` does all
but the last; `./setup --teardown` stops ergostat, the exporter and Prometheus (the downloads, the clone
and the record stay; `ergostat reset --yes` clears the record).

Then give it work, as a test:

```bash
bin/demo_issues.py create              # a test issue in JIRA_PROJECT, labelled JIRA_LABEL (at most 3 at once)
bin/tickets.py list                    # where each ticket is
ergostat actions                       # what waits for your approval (and every action, counted per class)
ergostat actions ID --approve          # approve one: ergostat runs it, and its step finds it done (--deny: never)
bin/demo_issues.py cleanup --delete    # close the demo's open pull requests, delete their branches and issues
```

`bin/demo_issues.py` is the test harness, not the factory: it writes down what it created
(`SCRATCH/created.json`) and cleans up only that. Never run it at work.

**Offline.** Without a `factory.conf` (a fresh copy), or with `TF_OFFLINE=1`, nothing leaves the folder:
Jira and GitHub are the fakes in `bin/fakes.py` (issues arrive on their own; the repository is a local bare
repository whose CI runs the sample's own check), the work is the stand-in's, the scripted teammate also plays
you and approves every held action, and the timings are seconds. `ergostat run` and watch it go round;
`scripts/demo_check.py ticket-factory` runs it that way.

## The steps

The workflow is one item kind, `ticket`. Its `states` (in `ticket.yaml`) are the step list, and each step is a
file in `steps/`: the stock of tickets that step leaves behind, the flow it moves them along, the goal that runs
it ("nothing waits here"), and its block, which takes the tickets waiting in its state:

```yaml
blocks:
  open-pr:
    type: program
    goal: worked-opened
    daemon: steps                                              # its runs handed to the steps' daemon (below)
    takes: {kind: ticket, at: worked, to: [pr-open, stopped]}   # a run per ticket that reaches worked
    pool: 3                                                    # three tickets at once
    workspace: code                                            # the ticket's worktree (ERGOSTAT_WORKSPACE)
    actions: [git-push, open-pr, jira-transition, jira-comment] # what its runs may ask for
    out: flow.open-pr
```

ergostat starts a run for each ticket that reaches `at`, holding a lease on it (the ticket is `leased` meanwhile:
its step's stock counts it before and after), and hands it to the steps' daemon, `bin/step.py serve`; the AI steps
run `bin/step.py NAME`, a process each. Either way the step's script (`steps/NAME.py`) runs for the ticket the run
holds (`ERGOSTAT_ITEM`), and its `run(ticket)` returns:

- `Move(fields)`: done; `ticket.NAME` is recorded, which the kind's `on:` maps to the next state (a state in `to`:
  the lease ends, acked);
- `Wait(why)`: not yet (an approval, a reviewer, CI); the ticket is given back, not counted, and looked at again
  soon: after `RECHECK_FIRST` (1 s), doubling each time in a row it waits at that step, at most `POLL_EVERY`
  (`{"nack": {"why": ..., "after": "2s", "count": false, "news": true}}`), and **at once** when there is news of it
  (below, "Pushed, not polled"). `Wait(why, due=S)`: no later than S seconds (the review step's re-ping);
- `Stop(why)`: it cannot go on (an action denied or failed, a repository not its own); the ticket moves to
  `stopped`, for you (`bin/tickets.py retry KEY` sends it back).

A step that crashes (exits non-zero) has its attempt counted; after three (`lease: {attempts: 3}` on the kind, two
on the AI steps) the ticket is a dead letter, `dead`: `ergostat lease` lists them, and `ergostat lease ITEM
--redrive` gives one another go once its cause is fixed. A run silent past its lease's TTL (5 minutes for the
program steps, 20 for the AI ones) loses its ticket to the next run, and anything it says about it afterwards,
gated actions included, is refused.

| # | Step | From → to | What it does | Gated actions |
|---|---|---|---|---|
| | watcher | → `new` | `bin/watch.py`, a sensor's daemon: the issues in `JIRA_PICK_FROM` labelled `JIRA_LABEL` become tickets; Jira's links on them are recorded as the ticket's relations `blocked_by`, `duplicates`, `relates_to` and `parent` (`ticket.linked`, below) | none (reads) |
| 1 | `pick-up` | `new` → `picked` | the issue to In Progress, by whichever transition the project has (looked up, never assumed) | `jira-transition` |
| 2 | `locate` | `picked` → `located` | the repository the issue names (`repo: owner/name`, or a GitHub link), else `GITHUB_REPO`; any other stops it. Its clone (`run/repo`) made or fetched | none |
| 3 | `work` | `located` → `worked` | in the ticket's workspace (a worktree from the pool `code`, on `ergostat/KEY-slug`), the AI agent does the issue (`prompts/work.md`), or the stand-in writes a file; committed. Its cost is recorded | none: the agent cannot push or call gh |
| 4 | `open-pr` | `worked` → `pr-open` | push; the pull request, its description linking the issue and saying who did it and for how much; the issue to In Review, with a comment linking the pull request | `git-push`, `open-pr`, `jira-transition`, `jira-comment` |
| 5 | `ask-review` | `pr-open` → `review-asked` | a review request to `REVIEWERS`, or with none a comment asking | `request-review` or `pr-comment` |
| 6 | `review` | `review-asked` → `approved` or `changes-asked` | reads what people wrote (whatever the factory did not mark as its own): an approval (or a comment starting `APPROVE_WORD`) approves; anything else asks for a change. No answer within `REPING_AFTER`: re-ping, at most `REPING_MAX` | `pr-comment` (re-pings) |
| 7 | `address` | `changes-asked` → `review-asked` | in its workspace, the agent answers the comments with a change (`prompts/review.md`), pushed, and a reply saying what it did | `git-push`, `pr-comment` |
| 8 | `sail` | `approved` → `sailed` | the `SAIL_LABEL` label | `pr-label` |
| 9 | `ci` | `sailed` → `ci-green` or `ci-failed` | CI on the pull request's head (GitHub Actions); a failure keeps its log | none (reads) |
| 10 | `fix-ci` | `ci-failed` → `sailed` | in its workspace, the agent triages the log and fixes it (`prompts/ci.md`), pushed, and a comment saying what failed; with nothing to fix, the run is run again | `git-push`, `pr-comment`, `ci-rerun` |
| 11 | `merge` | `ci-green` → `merged` | merged (`MERGE_METHOD`) if `MERGE=yes` and the repository allows it; otherwise, or when you deny it, it stops at approved and says why (`merged: false`) | `pr-merge` |
| 12 | `close` | `merged` → `done` | the issue to Done, with a comment: the pull request, merged or not, the cycle time, re-pings, CI failures, the AI's cost. Its workspace is cleaned by ergostat | `jira-transition`, `jira-comment` |
| | `reporter` | | every 30 seconds: the daily summary and the OKR (below) | none |

The two rework loops are drawn as such: a review that asks for a change sends the ticket back round
`address` → `review`, and a failed CI run round `fix-ci` → `ci`.

The **scripted teammate** (`bin/teammate.py`, `factory/world.yaml`, drawn in the review system) plays the reviewers here: it looks at a
pull request `TEAMMATE_AFTER` after the review was asked for (so the review step re-pings first), asks for
one change in a review, and approves with `/approve` once the factory has answered (one GitHub account cannot
approve its own pull request). At work, `TEAMMATE=no`: your reviewers are people, and their real approvals
count. The stand-in leaves an empty notes file (`STANDIN_PLACEHOLDER=yes`) so the repository's CI fails
once and `fix-ci` has something to fix.

## Workspaces

```yaml
workspaces:                          # ergostat.yaml
  code:
    repo: run/repo                   # the clone; locate makes it and fetches it
    size: 3                          # three tickets' worktrees at once
    branch: "ergostat/{id}-{slug}"   # ergostat/SCRUM-12-fix-the-login-page
    base: origin/main
messages:
  done: {ticket: [done]}             # finished here: its workspace is cleaned
```

The blocks with `workspace: code` (`work`, `open-pr`, `address`, `fix-ci`) get the ticket's worktree: made on its
first run from `base` on the ticket's branch, and given back as it was on every later one (a retry, the answer to a
review, a CI fix). Between them it is **held** for the ticket; once the ticket is `done` (or a dead letter), ergostat
**cleans** it (detached, untracked files removed; the branch stays in the clone) for the next ticket. A ticket that
`stopped` keeps its workspace, for a retry. With all three out, a ticket waits in `located` (its run is put off ten
seconds, not counted as a failure). `ergostat workspaces` lists them; one found dirty or broken is quarantined, never
reused, until you free it (`ergostat workspaces code --free N`).

An `ai` block's own `claude -p` would start in the workspace; here the block's `run:` is `bin/step.py`, which runs in
the model's folder and passes `ERGOSTAT_WORKSPACE` to `bin/agent.py`, which starts Claude Code there.

## Gated actions: what is gated, and how to promote one

Every write to Jira or GitHub is a named action in `factory/actions.yaml`, a command template and its gate:
`approve` (held until you approve it), `auto` (run at once) or `deny` (never). All are `approve` as shipped:

| Action | Command (ergostat runs it) | Asked for by |
|---|---|---|
| `jira-transition` | `bin/jira.py transition {key} {status}` | pick-up, open-pr, close |
| `jira-comment` | `bin/jira.py comment {key} {text}` | open-pr, close |
| `git-push` | `git push --force-with-lease origin HEAD:refs/heads/{branch}`, in the workspace | open-pr, address, fix-ci |
| `open-pr` | `bin/github.py open-pr {repo} {branch} {title} {body} {base}` | open-pr |
| `request-review` | `bin/github.py request-review ...` | ask-review (with `REVIEWERS`) |
| `pr-comment` | `bin/github.py comment {repo} {pr} {body}` | ask-review, review (re-pings), address, fix-ci |
| `pr-label` | `bin/github.py label {repo} {pr} {label}` | sail |
| `ci-rerun` | `bin/github.py rerun {repo} {run_id}` | fix-ci |
| `pr-merge` | `bin/github.py merge {repo} {pr} {method}` | merge |

A step asks with `act(name, **args)` (`bin/gated.py`, which runs `$ERGOSTAT_CMD act NAME --arg K=V`). An `approve`
action is held: the step waits `ACT_WAIT` (10 seconds) for you, then gives its ticket back and asks again on its next
run, where the same request (the same action and arguments) is the same action, never a second one. You answer with
`ergostat actions ID --approve` (or `--deny`, with `--note`), or Approve / Deny on the action's page; ergostat runs
it at once, and the step finds it done, its output with it. An action that ran is never run again; one that failed
stops its ticket. A denied action stops its ticket too, except the merge, whose denial means "stop at approved".

Every request and answer is an `ergostat.action/...` item (`ergostat.action.requested`, `.approved`, `.ran`, ...):
who approved what, when, the exact command and its output. The ones held are a stock, `actions-waiting`
(`ergostat.actions.held`), held at 0 by a person block, `approve` (you), which asks while anything waits.

**Promoting a gate** is your edit to the model: `gate: auto` on the action in `factory/actions.yaml` (ergostat
reloads it as it runs). `ergostat actions` counts each class's approvals this week and says when one has been
approved five times or more and never denied. A local promotion you don't want to commit stays a local edit.

**What is enforced.** ergostat runs the actions, in its own process with its own environment, so a step needs no
write credentials of its own; the steps' code makes no write except through `act`. But nothing stops a step's script
from calling `gh` or Jira itself: it runs as you, with your sign-ins, and the gate holds only the acts that go
through it (SPEC 12k, "From a program block"). The steps here also read Jira and GitHub with the same sign-ins. To
make the gate a wall, run the steps' command as another user, or in a container, with read-only credentials, and
leave the write credentials to the user running ergostat. Whatever the gate, `bin/jira.py` refuses to write to an
issue without `JIRA_LABEL`, and `bin/github.py` to any repository but `GITHUB_REPO`. The AI agent is held by its own
Claude Code flags (`bin/agent.py`: file tools and read-only git, no `git push`, `gh` or `curl`), not by ergostat's
OS sandbox, which only a session ergostat starts (`ergostat session`) gets.

## Adding a step

A YAML change, and a script if the step acts. Say a `lint` step between `work` and `open-pr`:

1. In `ticket.yaml`, add the state `linted` after `worked` in `states`, and `ticket.lint: linted` in `on`.
2. Copy a step file: `cp steps/08-sail.yaml steps/03b-lint.yaml`, and in it name the stock `linted`, the flow and the
   block `lint` (`from: worked`, `to: linted`), the goal on the stock `worked`, and the block's
   `run: python3 bin/step.py lint` and `takes: {kind: ticket, at: worked, to: [linted, stopped]}`. Give it
   `workspace: code` if it reads or changes the code.
3. In `steps/04-open-pr.yaml`, the next step now starts where lint ends: `takes: {at: linted, ...}`, its flow
   `from: linted`, and its goal on `linted`.
4. Optionally, `steps/lint.py`, with `run(ticket)` returning `Move(fields)`, `Wait(why)` or `Stop(why)`. With
   no script, the step moves every ticket on at once: a state for a person or a program outside to act on. An
   outward act is `act("name", arg=value, ...)` (`from gated import act`): add the action to
   `factory/actions.yaml` (its command and gate) and its name to the block's `actions:`.

`ergostat check` says what is not connected; ergostat reloads the model while it runs.

## Adapting it at work

The owner's work agent (the Supervisor, or whoever sets it up) copies the folder and changes three things:
`factory.conf`, the credentials, and the gates. Set `TEAMMATE=no` (the reviewers are people), and never run
`bin/demo_issues.py` there.

**Jira Data Center.** Everything Jira is in `factory.conf` and `bin/jira.py`, one function per call (`waiting`,
`counts`, `get`, `transitions`, `transition`, `comment`):

- `JIRA_URL`, `JIRA_PROJECT`, `JIRA_LABEL`, and the status names (`JIRA_PICK_FROM`, `JIRA_IN_PROGRESS`,
  `JIRA_IN_REVIEW`, `JIRA_DONE`). Transitions are looked up by the status they lead to, so a project's own workflow
  works as long as it has those statuses (`./setup` checks).
- `JIRA_API=2` and `JIRA_AUTH=bearer`, with a personal access token in `JIRA_TOKEN_FILE`. The differences are marked
  `DC` in `bin/jira.py`: search is `GET /rest/api/2/search` (Cloud's is `POST /rest/api/3/search/jql`), and comment
  bodies are plain text (Cloud's are Atlassian Document Format). A different scheme (a custom field for the
  repository, a JQL of your own) is a change to `_scope`, `waiting` or `_issue` there.
- GitHub Enterprise: `gh auth login --hostname ...` and `GH_HOST`. Another code host is `bin/github.py`, one function
  per call, and the commands the actions run.

**Credentials.** The Jira token is read from `JIRA_TOKEN_FILE` at each call, never printed, logged or recorded;
`gh` uses its own sign-in. Both are used by the actions ergostat runs (writes) and by the steps (reads). With
read-only credentials available, give the steps those (run their command as another user), and keep the write
credentials with ergostat alone (above).

**Gates.** Start with every action at `approve`, as shipped, and approve from `ergostat actions` or the page. As a
class proves itself (`ergostat actions` says when), promote it to `auto` in `factory/actions.yaml`; keep `deny` for
what the factory must never do there (`pr-merge: {gate: deny}` makes every ticket stop at approved). A class of your
own (`class: jira-write` on both Jira actions) is counted, and promoted, as one.

## Daemons

A `run:` sensor starts a process for every reading, and a `run:` block one for every run. Here that added up: the
three measures and the watcher every 10 seconds, the teammate every 5, and each ticket waiting on a reviewer or CI
looked at again every few seconds, each a Python process that loaded the factory's modules and, to read the record,
ran `ergostat item` (which loads the model): offline, about 190 Python starts a minute. So the factory runs those
parts as **daemons** (`docs/DAEMONS.md`): programs ergostat starts once and keeps running, handed each reading or run
as a line of JSON on their standard input, which answer with lines on their standard output. Each one, in the shapes
`docs/DAEMONS.md` names:

| Daemon | Shape | Serves | Why a daemon |
|---|---|---|---|
| `measures` (`bin/measure.py serve`, `factory/oversight.yaml`) | one for several sensors, named under `daemons:` | `ai-spend`, `repings`, `cycle-hours` | they read the same source, the record: the readings asked at the same moment share one read of it |
| `sensor.arrivals.main` (`bin/watch.py serve`, `factory/intake.yaml`) | a sensor's own, inline | the arrivals flow | the one sensor that reads Jira, kept apart from the rest; Jira being down fails its readings (each says why), and nothing else |
| `steps` (`bin/step.py serve`, `ergostat.yaml`) | a block daemon, named, shared by blocks | the nine short steps | their runs are frequent and over in a moment; each ticket's run on a thread of its own, 27 at once (the nine pools) |
| `block.teammate` (`bin/teammate.py serve`, `factory/world.yaml`) | a block's own, inline | the teammate | a look every 5 seconds, with no process each |

`bin/daemon.py` is their side of the protocol, shared: a reader that only hands lines on (so a slow Jira or step
never keeps it from the next line or a cancel), readings asked together answered together, each run on a thread with
its own `ERGOSTAT_*` values taken from its line (`tf.env`: never set in the process, where the next run would find
them), every line tagged with its run, a `cancel` answered at once, and a heartbeat. The daemons read the record over
ergostat's socket (`ERGOSTAT_SOCKET`), not by starting `ergostat item`. The watcher records each new ticket as the
sensor's own (`ticket.found`, source `arrivals.main`), exactly as when its command printed it.

The watcher also records **Jira's links** as the ticket's relations (`ticket.yaml`), at each reading, as the sensor's
own (`ticket.linked`, source `arrivals.main`; a sensor may record any event, SPEC §9.3 limits only runs started by
events). It asks Jira once more per reading (every 10 seconds, so 6 more searches a minute, for `issuelinks` and
`parent` of every labelled issue). Matched by the link type's **name**, as Jira's default scheme calls them: `Blocks`
seen from the blocked side (`inwardIssue`) is `blocked_by`; `Duplicate` seen from the duplicate (`outwardIssue`) is
`duplicates`; the other side of these two is the inverse, which ergostat derives (`blocks`, `duplicated_by`), so it
is not written. Any other type, either way, is `relates_to`, held by each ticket on its own side. A type renamed by an
admin is then `relates_to` too. `fields.parent` is `parent`: on Cloud an epic or a sub-task's parent. On Data Center
an epic is the Epic Link custom field, which is not read, so there only a sub-task's parent is recorded. A parent the
factory never found stays an id never recorded. Each relation is written as a whole set (`{"set": [...]}`) when it
differs from the ticket's fold, so a link removed in Jira is removed here. What it does not promise:
- **Caught up after the next reading, not at once.** No lock is taken: each reading compares Jira's answer with the
  fold as read at that reading. Two readings that overlap (the daemon and a manual `watch.py` whose output is
  recorded) can land the older answer last, and the record then matches Jira's latest answer again after the next
  reading.
- **Tickets only.** A labelled issue the watcher never found is not given links (`ticket.linked` makes no item).
- **The first 500 labelled issues** (`LINKS_MOST`; the search is paged, Jira answering 100 or fewer a page). An issue
  past them is not looked at and keeps the links it has.
- **An issue with a link or parent that can't be read** (no key, no type name, neither side, a key that is not
  `PROJ-123`) keeps the links it has, and the watcher's log says so at each reading. A search that fails writes
  nothing.
- **Only what the Jira account can see.** Jira leaves out a link to an issue the account may not see, so such a link
  looks removed and is cleared.

**What stays a process each**, on purpose:

- **the AI steps**, `work`, `address` and `fix-ci` (`type: ai`): a session of seconds to minutes, beside which a
  process start is nothing. A run of its own keeps one session's crash or memory from the others, a cancel stops the
  whole session, and its CPU, memory and AI cost are measured per run (a daemon's are measured only as a whole);
- **the `reporter`**, every 30 seconds: it writes the day's report, rarely enough that a process is the simplest
  thing.

Every event type, series, stock, flow, item kind and state is what it was; only `run:` lines became `daemon:`, so a
record made before still replays, and the estimates and projections read it as before.

**What changes with them.**

- **Costs are the daemon's.** The Agents page lists each daemon: its state, process, restarts, CPU and memory. A run
  handed to a daemon records its wall time only: the nine short steps no longer have CPU and memory per run (the
  series `run/<step>/cpu` and `run/<step>/memory` stop; `run/<step>/seconds` goes on). The AI steps' still do.
- **Logs.** What a daemon logs goes to `logs/daemon-NAME.log` in the state folder (`~/.ergostat/<project>/`): the
  short steps' lines are in `daemon-steps.log`, not each block's log.
- **Timeouts and cancels.** A run handed to a daemon is cancelled after 300 seconds unless its block says
  `timeout:` (a run of its own had none but its lease's 5 minutes), and when its lease expires or you stop its block.
  The cancel is answered at once; anything the run still asks for after it, a gated action included, is refused (its
  lease is gone). A cancelled run still going 10 seconds later (`CANCEL_GRACE`) is stuck, a hung call: the daemon
  ends, ergostat starts it again, and the runs it held are taken again. Calls outside are bounded too: git and `gh`
  give up after `GIT_TIMEOUT` (5 minutes), Jira after 30 seconds.
- **Restarts.** A daemon that crashes is started again after a back-off; one that keeps crashing is given up, with an
  alarm (`ergostat status`), until `ergostat block steps --restart` (the daemon's name, or one of its blocks') or a
  change to the model.
- **Settings and code.** A changed setting in `factory.conf` is read again at the next reading or run, and a step's
  script (`steps/NAME.py`) afresh on every run. Going online or offline (`factory.conf` made or removed,
  `TF_OFFLINE`), `SCRATCH`, and any edit to `bin/` need the daemons started again: `ergostat block steps --restart`,
  `ergostat block measures --restart`, and so on (or `ergostat run --stop` and `ergostat run`). To try one by hand, pipe lines into it from this folder
(`docs/DAEMONS.md`, "Testing a daemon by hand"):

```bash
printf '%s\n' '{"op": "read", "sensor": "repings.main", "request": "1"}' '{"op": "stop"}' | python3 bin/measure.py serve
python3 bin/measure.py repings          # the same measure, once, to compare
```

## Pushed, not polled

A step that waits on someone outside (a reviewer, CI, an approval) used to give its ticket back for `POLL_EVERY`
(15 s) and ask again; most of a ticket's time went there (docs/proposals/latency.md). Now:

- **News wakes it.** A `Wait` gives the ticket back with `news: true`: the first event about the ticket that its own
  runs did not cause makes it ready at once (SPEC 9.5). At work, that event is GitHub's (or Jira's) webhook, pushed to
  ergostat and mapped to the ticket by its branch (SPEC 5c):

  ```yaml
  # ergostat.yaml, as shipped (intake: belongs in the main file)
  intake:
    hooks:
      github:                          # GitHub: Settings → Webhooks → https://<forwarded>/api/hooks/github,
        event:                         #   content type JSON, secret: the token in <state>/intake.token
          from: "header:X-GitHub-Event"
          map: {pull_request_review: ticket.news, issue_comment: ticket.news, check_suite: ticket.news,
                check_run: ticket.news}
        item: "ticket/{pull_request.head.ref~^ergostat/([A-Z][A-Z0-9]*-[0-9]+)}"
        id: "{header:X-GitHub-Delivery}"
        data: {news: action}
      jira:                            # Jira: a webhook on the project's issues, ?token=<the token> in its URL
        event: {from: webhookEvent, map: {"jira:issue_created": ticket.news, "jira:issue_updated": ticket.news}}
        item: "ticket/{issue.key}"
        id: "jira-{issue.id}-{timestamp}"
        data: {news: webhookEvent}
  ```

  (CI's `check_suite` names its branch elsewhere: `github-ci` in `ergostat.yaml` maps it, as a second GitHub
  webhook.) Offline, the scripted teammate records the same news (`ticket.news`, as `github`) when it reviews and
  when it approves.
- **Short, adaptive re-checks** when nothing pushes: 1 s, 2 s, 4 s ... up to `POLL_EVERY`, so a CI run of a few
  seconds is seen within a second or two of finishing, while a review that takes an hour costs a re-check every
  `POLL_EVERY`, as before.
- **No model load per call.** `bin/tf.py` and `bin/gated.py` ask the running ergostat over its socket
  (`ERGOSTAT_SOCKET`) for the ticket, to record an event and to ask for an action; an action approved is answered
  at once, not at the next half-second look. Without a running ergostat they run the commands, as before.
- **Approvals are people.** A gated action held for approval waits for the owner (offline, the scripted stand-in
  approves every 5 s): that is outside time. Promoting a class to `auto` (above) is how it goes.

## Measurements

In ergostat (the page, `ergostat loop`, `ergostat item --kind ticket`):

- **stocks**, counted from the tickets: one per state (`new`, `picked`, ... `review-asked`, `changes-asked`,
  `ci-failed`, ..., `done`, `stopped`), the actions held for approval (`ergostat.actions.held`), and three read from the record by
  the daemon `measures` (`bin/measure.py`): `ai-spend` (dollars), `repings`, and the reports written;
- **flows**: each step's, counted as tickets enter its state, arrivals measured by the watcher, and the AI
  spending as each session ends;
- **auxiliaries**: `prs-awaiting-review` (open and not approved), `cycle-hours` (the median from found to
  Done), and, once `./setup` has run, three read back from Prometheus (`local/prometheus.yaml`): the issues
  In Progress or In Review as Jira counts them, the factory's pull requests open as GitHub counts them, and
  the dollars per session. The record says what the factory did; these say what the services saw.
- **per ticket**: `repings`, `review_rounds`, `ci_failures`, `ai_cost_usd`, `ai_runs`, `ai_seconds`, each
  session's answer (`sessions`, `last_session`), its time in each state, and `cycle_hours`.

In Prometheus (`bin/exporter.py`, scraped every 15 seconds): `tf_tickets{state}`, `tf_prs_awaiting_review`,
`tf_actions_waiting`, `tf_ci_failures_total`, `tf_repings_total`, `tf_review_rounds_total`,
`tf_ai_cost_usd_total`, `tf_ai_sessions_total`, `tf_ai_seconds_total`, `tf_cycle_seconds_sum` / `_count`,
`tf_step_seconds{state}` (the longest wait in each state), and from the services every minute
`tf_jira_issues{status}` and `tf_github_open_prs`.

**Equations**, where the flows are clear, so projection and what-if show something (the Model page): each
step drains its stock at a rate set by how long it takes (`stock.located / work-time`), the review splits
into approvals and changes by `change-share` over `review-time`, CI into passes and failures by
`ci-fail-share` over `ci-time`, and the AI spending is a coflow of the sessions
(`cost-per-session * (flow.work + flow.address + flow.fix-ci)`). The times and shares are marked
`estimate: true`: the Fit page proposes values from the record, and nothing changes until you accept one.
Try a what-if on `review-time` (a slower team) or `ci-fail-share`, and watch `prs-awaiting-review`.

## The daily summary and the OKR

`bin/report.py` (the `reporter` block) keeps two items:

- `report/<date>`: `reports/<date>.md`, rendered on the Items page: what was Done today (each with its pull
  request, merged or not, cycle time, re-pings, CI failures, AI cost), what is in flight by state, what waits
  for your approval, what stopped and why, the AI's sessions and cost, and the OKR;
- `okr/<year>-Q<n>`: the objective ("labelled tickets go from pick-up to Done with no hands on the
  keyboard"), five key results against their targets (Done this quarter, median cycle time, re-pings per
  pull request, the share passing CI first time, AI dollars per ticket: `OKR_*` in `factory.conf`), and its
  state, `on-track`, `at-risk` or `off-track`, from how many are met.

## Costs measured

Runs on 2026-11-18 against the real services (Jira Cloud project SCRUM, the test repository
`danroblewis/orchestra-live-delivery` and its GitHub Actions CI, a Prometheus of the example's own), on ergostat's
leases, workspace pool and gated actions, one test issue each, created by `bin/demo_issues.py` and deleted after:

| Run | The work | Gates | Actions | AI sessions | AI cost | Cycle time | Re-pings | Review rounds | CI | End |
|---|---|---|---|---|---|---|---|---|---|---|
| stand-in | `AI=standin` | all `approve`, answered with `ergostat actions ID --approve`; `pr-merge` denied | 14 approved and run, 1 denied | 3 (stand-in) | $0 | 3.9 min | 1 | 1 | failed, fixed, green | stopped at approved, issue Done |
| haiku | `AI=claude`, haiku | all promoted to `auto` | 13 run by their gate | 2 (work, review) | $0.0089 | 3.3 min | 1 | 1 | green first time | merged, issue Done |
| haiku, CI failing | `AI=claude`, haiku (the issue asked for an empty placeholder) | all `auto` | 15 run by their gate | 3 (work, review, CI fix) | $0.0143 | 4.0 min | 1 | 1 | failed; haiku read the log and removed the empty file; green | merged, issue Done |

A haiku session here costs about half a cent and takes about ten seconds; the cycle time is set by the people
(the scripted reviewer's `TEAMMATE_AFTER`, two minutes, and the owner's approvals) and by CI, not by the AI. Each
ticket's workspace was made at `work`, held through review and CI, and cleaned at `done`; no run failed and no ticket
became a dead letter.

## Files

| | |
|---|---|
| `setup` | the one command: set up, run, `--teardown` |
| `factory.conf.example` | every setting, with its default (copied to `factory.conf`) |
| `ergostat.yaml`, `ticket.yaml` | the model's top and the workspace pool; the item kinds (the step list) |
| `steps/` | one YAML file and one script per step |
| `factory/` | the gated actions (`actions.yaml`), arrivals (`intake.yaml`), the owner's view (`oversight.yaml`), the teammate (`world.yaml`) |
| `local/` | `prometheus.yaml`, written by `./setup` from `prometheus.yaml.in` |
| `prompts/` | what the AI agent is asked: the work, a review, a CI failure |
| `bin/jira.py`, `bin/github.py` | every call to Jira, every call to GitHub (and the actions' commands) |
| `bin/gated.py` | a step's outward act: `act(name, **args)`, through `ergostat act` |
| `bin/step.py` | the step runner: `serve`, the steps' daemon; `NAME`, one run (the AI steps) |
| `bin/daemon.py` | the daemons' side of ergostat's JSON lines, shared by the four daemons |
| `bin/agent.py` | Claude Code or the stand-in, and what each session cost |
| `bin/watch.py`, `bin/measure.py`, `bin/exporter.py` | the sensors' daemons, and the measurements for Prometheus |
| `bin/report.py` | the daily summary and the OKR |
| `bin/teammate.py` | the scripted reviewer (and, offline, the owner's approvals) |
| `bin/tickets.py` | the tickets, and `retry` for a stopped one |
| `bin/demo_issues.py` | the test harness: the demo's own issues, and cleaning up after them |
| `bin/fakes.py` | Jira and GitHub, offline |
