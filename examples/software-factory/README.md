# A software factory and the software it builds

AI agents write the code, and the code serves customers. Both are modelled as one system, so
you can see how the factory's parts (its queues, how carefully it reviews, how often it ships)
show up in what customers get.

- **The product** is textkit, a small library of text operations (`slugify`, `word_count`,
  `camel_case`, ...). Customers call it, the market (`world/`) judges every answer, and users
  come or go by how often the answers are right. It starts with two bugs, and customers want
  more operations than it has.
- **The factory** turns tickets into releases. Support files a bug ticket when customers report
  an operation broken. The product manager files a feature ticket for an operation they ask for
  that does not exist. A **developer** and a **reviewer**, AI agents (Claude Code) or free
  stand-ins, work the tickets in real git branches. A deployer ships what is merged.

## Run it

Work on a copy: running it writes the product's repository and production into `run/`.

```bash
cp -r examples/software-factory /tmp/factory && cd /tmp/factory
ergostat run                     # stand-in agents: free, seconds per ticket
FACTORY_AI=claude ergostat run   # Claude Code sessions do the developing and reviewing (real tokens)
```

Open the page `ergostat run` prints, or use the command line:

```bash
ergostat loop                    # every goal: holding or off, and how fast it comes back
ergostat item --kind ticket      # the tickets, by state
ergostat explain no-live-bugs    # the whole loop, part by part
ergostat run --stop
```

With the stand-ins, a minute shows the first bugs fixed, and a few minutes show the product
growing into its market. With Claude, a ticket takes the developer and the reviewer about 20
seconds each.

## The two systems

The diagram starts with each system as one box: its ports are what crosses its edge (the
product's stocks going out to support and the product manager, the deploys coming in). ▸ opens a
box in place, ⤓ draws it alone with what it reaches outside at its edge. The factory is itself
two systems, `intake` (tickets filed into the backlog) and `delivery` (developed, reviewed,
deployed); `ergostat explain system.delivery` says what goes in and out of it.

**The factory** (`factory/`, its items in `factory.yaml`) is made of items: `ticket/12`, `pr/7`, `release/3`, each folded
from its events. Its stocks are counted from them, with no sensor program at all:

| stock | counts | goal |
|---|---|---|
| backlog | tickets open or being worked | `backlog-clear`: the developer works while it is above 0 |
| in-review | tickets waiting for review | `reviews-done`: the reviewer works while it is above 0 |
| awaiting-deploy | tickets merged, not live | `all-live`: the deployer ships, at most every 30s |
| oldest-bug | hours the oldest unshipped bug has waited | (watched) |

A rejected review sends its ticket back to the backlog (`rejected`, the rework flow).

**The product** (`product.yaml`) has the stocks customers live with:

| stock | what | goal |
|---|---|---|
| bugs-live | operations in use that answer wrong or fail | `no-live-bugs`: none (critical) |
| missing-ops | operations asked for that do not exist | `few-missing`: at most 1 |
| users | who stays | `users-growing`: at least 180 of a market of 250 |

Nothing pipes a release into the product. A deploy *drives* the product's flows: it fixes what
was broken (`fixes`), ships what was missing (`shipped`), or breaks what worked (`regressions`).
`driven-by:` says so, and the page draws it as a dashed arrow.

## The loops, the long way round

No block acts on the product's stocks directly, yet each of its goals closes a loop. The loop
runs through every queue in the factory:

```
bugs-live ─ support ─▶ backlog ─ developer ─▶ in-review ─ reviewer ─▶ awaiting-deploy ─ deployer ─▶ deployed ┄▶ fixes ─▶ bugs-live
```

`ergostat explain no-live-bugs` prints it. The loop answers only as fast as each queue drains:
a slow reviewer or a deployer that ships once an hour is a delay in the product's own loop.
`users-growing` closes through the product manager, the same factory, and `missing-ops`.

There are three balancing loops (bugs, missing operations, users) and one that pushes the other
way: more users ask for more of the long tail (`asks`, driven by `users`), which fills
`missing-ops` and loads the factory. The product grows until the factory's capacity, or its
quality, holds it back.

The market itself, the block `customers`, is not ours to command. `check` lists it as acting on
its own (an open loop), and that is right.

## What to try

The stand-ins make mistakes on purpose, and how often is yours to set:

```bash
FACTORY_DEV_QUALITY=0.4 ergostat run    # the developer often misses a case (input with digits)
FACTORY_DEV_CARELESS=0.5 ergostat run   # and often "tidies" a shared helper, breaking other operations
FACTORY_REVIEW=lax ergostat run         # the reviewer only checks the tests pass
FACTORY_REVIEW=rubber ergostat run      # the reviewer approves everything
```

A strict review turns the developer's mistakes into rework: the `rejected` flow rises and
`in-review` waits. Customers never see those mistakes. With a lax review they reach production,
`regressions` rise, support files bugs, the backlog grows, and users settle lower. The page's
Items tab shows each ticket's path (the regressions are titled "... again"), and `oldest-bug`
shows how long customers waited.

In the YAML: give the deployer `every: 5m` and watch `awaiting-deploy` fill and `no-live-bugs`
take five minutes longer to come back. Or slow the developer (`FACTORY_PACE=20`): the factory has
one developer and one reviewer, and when the long tail arrives faster than they work, `backlog`
and `missing-ops` stay off together. That is the factory's capacity, read off the product's
goals.

## What is real and what stands in

- The product, its repository (`run/product`, a branch per ticket), its tests, production
  (`run/prod`) and every customer request are real. The market judges answers against
  `world/oracle.py`, which the agents never read.
- The stand-in developer writes the right code with the chance you set, because it peeks at the
  oracle (it stands in for "the ticket's description was enough"). The stand-in reviewer checks
  the ticket's own examples and failures. With `FACTORY_AI=claude`, both are Claude Code sessions
  that get only the ticket, the code and the tools (`bin/factory.py`), and their prompts are in
  `prompts/`.
- Every step is an event about an item, recorded by `bin/factory.py` through `ergostat event --add`.
  The Record and Items pages show the factory as it ran.
