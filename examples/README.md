# Examples

Each folder is a whole system: an `ergostat.yaml` and the programs its blocks run. Run one with
`cd examples/<name> && ergostat run`; its page's address is printed. They keep their files inside their
folder (each ignores what it writes), and their records in `~/.ergostat/` like any project.

| Example | What it is | Shows |
|---|---|---|
| [`first-loop`](first-loop/) | Your first loop: an inbox folder kept short | one-line agents, bare numbers, live reload, falling behind and recovering |
| [`plain-crontab`](plain-crontab/) | Two cron one-liners, no scripts | bare numbers, cron, `open_loop`, a disturbance named with its agent, the longest period that can hold |
| [`talking-scripts`](talking-scripts/) | Scripts that print sentences, used unchanged | `parse`, valve `max`, open loops, a declared disturbance rate |
| [`disk-space`](disk-space/) | One program, three roles | JSON lines, one agent filling sensor, controller and valve |
| [`file-queue`](file-queue/) | A folder as a queue | loops in series, folding, answer and recovery times, a load agent |
| [`git-hygiene`](git-hygiene/) | Branches pruned on a real repository | real git, event-triggered agents |
| [`backups`](backups/) | Nightly backups and off-site copies | events between agents, `on`, a declared disturbance rate |
| [`docs-fresh`](docs-fresh/) | Docs kept in step with the code | AI agents, the ladder, feedforward |
| [`deps`](deps/) | Two loops in series, a person behind | people filling roles, valve `max`, saturation, work piling up downstream |
| [`this-mac`](this-mac/) | This machine, measured for real | a person filling several loops, manual valves, read-only measurement |
| [`ops`](ops/) | A small platform, several systems | systems and outlines, a weekly status, snapshots |
| [`big`](big/) | 24 loops, for the layout | layout at scale |
| [`image-squeeze`](image-squeeze/) | A service that compresses images, and a lab of AI agents that optimises it | stocks and auxiliaries sorted by memory, two-way flows, integral control (a setting stepped as a stock), a tracking loop, progressive delivery with rollback, experiments as items, guardrails, real measurement; Claude Code agents (`FACTORY_AI=claude`) or stand-ins |
| [`software-factory`](software-factory/) | AI agents build a product; customers judge it | items (tickets, PRs, releases) counted as stocks, a factory and a product as one system, `driven-by`, loops that close the long way, real Claude Code agents (`FACTORY_AI=claude`) or stand-ins |
| [`coordinator`](coordinator/) | The Coordinator of a software factory, as `docs/proposals/coordinator/` designs it: a leased work queue, a capped pool of AI-agent stand-ins, the codebase and the owner, controlled by the quality cascade, dispatch, a lease watchdog, admission, the owner's attention budgets, externalising and consolidation | a control architecture as one model: a cascade (an outer block setting an inner goal's setpoint), a setpoint scheduled on the owner's presence, a mode as a stock, critical goals, external blocks for what ergostat does not run; the same blocks with the harness's policy (`COORD_POLICY=harness`) or the designed one; thirty-day closed-loop tests headless (`world/experiment.py`) |
| [`alert-triage`](alert-triage/) | Alerts triaged, investigated along three facets at once, joined, summarised, escalated to a person | the reference model of `docs/MODELLING-WELL.md`: units, descriptions and equations everywhere, a fan-out and a join drawn in the Process view, AI and person tiers, rework; `poor/`, the same modelled badly |
| [`the-job`](the-job/) | A senior engineer's and SRE's job: reviews, PRs, chat, pages, outages, flag ramps, secrets, customer tickets, documents, as one system | items of many kinds counted as stocks, the same two loops in every domain (prepare, then decide), person blocks that only ask, auxiliaries counting what is late, outputs as files (`file:` fields: the morning brief, the ledger), read-only toward the outside; a simulated world, or the owner's own GitHub PRs read with `gh` (`JOB_GH=1`) |

Start with `first-loop`, then `plain-crontab` and `talking-scripts`: scheduled jobs as they are.
Most of the rest are simulated (a `sim.py` keeps a made-up world), so they run on any machine;
`file-queue`, `git-hygiene`, `plain-crontab` and `talking-scripts` act on real files in their folder,
and `this-mac` only reads your machine.

`ai-controller.sh` is a controller filled by `claude -p`: see `docs/ai-agents.md`.

`scripts/demos.sh start` starts them all; `scripts/demo_check.py` runs a fresh copy of each and checks its page.
