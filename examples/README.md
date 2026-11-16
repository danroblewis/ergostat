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
| [`image-squeeze`](image-squeeze/) | A service that compresses images, and a lab of AI agents that optimises it | variables (process and manipulated), integral control, a tracking loop, progressive delivery with rollback, experiments as items, guardrails, real measurement; Claude Code agents (`FACTORY_AI=claude`) or stand-ins |
| [`software-factory`](software-factory/) | AI agents build a product; customers judge it | items (tickets, PRs, releases) counted as stocks, a factory and a product as one system, `driven-by`, loops that close the long way, real Claude Code agents (`FACTORY_AI=claude`) or stand-ins |

Start with `first-loop`, then `plain-crontab` and `talking-scripts`: scheduled jobs as they are.
Most of the rest are simulated (a `sim.py` keeps a made-up world), so they run on any machine;
`file-queue`, `git-hygiene`, `plain-crontab` and `talking-scripts` act on real files in their folder,
and `this-mac` only reads your machine.

`ai-controller.sh` is a controller filled by `claude -p`: see `docs/ai-agents.md`.

`scripts/demos.sh start` starts them all; `scripts/demo_check.py` runs a fresh copy of each and checks its page.
