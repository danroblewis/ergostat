# Owner item 19: an Agent show page (designer's notes)

## What a user sees today

Screenshots are in DESIGN/shots/: plan-agentshow-agents.png, plan-agentshow-work-panel.png, plan-agentshow-rule-panel.png,
plan-agentshow-person-panel.png, plan-agentshow-fixer-panel.png, plan-agentshow-sf-implementor.png,
plan-agentshow-job-agents.png, plan-agentshow-item-pattern.png and plan-agentshow-agent-route.png.

- An agent exists only as a side panel opened from a row on /agents (`openAgent`, web/static/details.js:218). It has
  no address of its own: `/agent/work` returns 404 (plan-agentshow-agent-route.png), and `agent` is not in `UI_PAGES`
  (web/server.py:35). A panel can't be linked, bookmarked or opened in a new tab.
- The panel never shows what the agent *is*. It shows only what it did:
  - **ai** `work` (ticket-factory): "Command: python3 bin/step.py work". Its prompt (`prompts/work.md`, a real
    briefing with `{key}`, `{title}` slots) is not shown or named anywhere. `spec/legacy.py:53` shows the prompt only
    when the block has no `run`, and then only as `(prompt: <first 60 chars>)`. The software-factory `developer` is
    the same (`bin/ai.sh developer`; prompts/developer.md is never shown).
  - **program** `fixer`: the command is a `.venv/bin/python -m ergostat.library.run modelling rules` line with an
    absolute path. The program behind it isn't shown or named.
  - **rule** `keep-located-worked`: "Description: implied by work's goal: located-worked. Runs: not run by ergostat.
    In window 0 runs. Log /private/tmp/…/keep-located-worked.log". There is no law, no setpoint, no release point, and
    an empty Recent runs table. The law *is* worked out for the Blocks diagram (`blockdiagram.block_fn`, shown as
    MathML by `openBlock`, blocks.js:1010), but the Agents page never uses it. On the live factory the rules are `expr`
    blocks such as `review-when: waiting * (1 - over) * (busy < min(pool, busy + room)) * (1 - full)`, the most
    load-bearing logic in the factory, and they're visible only in YAML.
  - **person** `approve`: no `ask` text (the-job and ticket-factory both write one), only "a person".
  - **decision / narrow-ai**: no demo has one. examples/docs-fresh has `picker: kind: decision`, and the intent
    judge becomes narrow-ai when it names a model (spec/ir.py:737). Their means of deciding exist in the record:
    `state.decisions()` tallies the decision words and the ladder hint says "decided 'wait' 92% of 40: a rule could
    fill it". That shows on Agents only as a hint line.
- The same panel contradicts itself ("Runs: not run by ergostat" beside "In window 0 runs" beside a chart of 28 runs).
  Q38/Q41 cover this.
- Agent names elsewhere are dead text: the item page's lease table "block" column (plan-agentshow-item-pattern.png),
  Recent runs, and the Blocks caption.
- The API (`/api/agents/NAME`, server.py:557) returns `agent` (name, kind, command, schedule), runs, a log tail and
  use. It returns none of the block's `params` (prompt, ask, expr, goal/until, table), its `where` (file:line), its
  machine (`agents:` entry: model, at-once), or its decision tally. The page can't show the specification until the
  API carries it.
- The live factory (:8798) answered no GET at all during this walk, not even /static/style.css, at 10 s, 20 s, 60 s
  and 120 s timeouts. The process (pid 9278) was at about 160 % CPU. This is owner item 2's evidence, not this item's,
  but the show page must not add a slow query: everything it reads is in the loaded spec, plus files under the model
  folder and one bounded decisions query.

## Judgement

The owner asked for this page explicitly, which overrides "no new pages" (owner-list, decisions). It also settles the
review's R12 step "after R4: decide on Agents": Agents stays as the index, and each agent gets a show page, as Items
has /items and /item/ID. The owner calls the item page "very good", so the agent page follows its pattern: a header
line of short fields laid out to flow, then sections. It isn't a panel and it isn't a wizard.

**Where the request and the review agree.** R4/Q65 want every block to carry its function, with the agent as a
caption. The rule section of the show page uses the same `block_fn` law, so a rule reads the same on Blocks and on its
page. Q28 and Q30 want the evidence's actor line built from the Agents counts. The show page becomes where that line
links. Q38 (how it is engaged, which goal it serves), Q39 (recent runs with item and outcome), Q40 (cost stated) and
Q41 (never ran / behind) all describe content that moves from the panel onto this page. The show page carries that
content through the same functions, so each quick fix lands in one place.

**Where they conflict.** Q12 says absolute log paths shorten to the file name, but the page should link the log. The
two combine: show the file name as a link to `/file/logs/NAME.log`, which resolves under the state dir and is refused
under a public name, where it should be. The review wanted fewer pages, but the owner overrides that for this page.
The side panel stays as the quick look on the Diagram, with "Open its page". On /agents, rows become real links to
the page, as /items rows are, which also removes the Q47 re-sort mis-click.

**The design, by rung.** The rung decides the specification section's heading and content:

| rung | "What it is" section |
|---|---|
| person | **What they are asked**: the `ask`, rendered as Markdown; how they answer (the Inbox, `ergostat block NAME --done`); the asks open now |
| ai | **Its prompt**: the prompt file (or inline text) rendered as Markdown, `{slot}` placeholders marked "filled per item"; then model, machine (at-once), tools/actions/read, workspace, emits; then **Its wrapper**, the `run` program highlighted (collapsed) |
| narrow-ai | **Its specification**: the prompt as above, then the fixed parts that make it narrow: model, the outputs it may give (out ports / emits / decision words), budget (`max-cost`), what it holds (kinds for an intent judge); ergostat's own (the intent judge) says so and shows its parameters |
| decision | **How it decides**: the question (prompt, or the program it runs), then the answers it gave in the window as a ranked tally with shares (`state.decisions`), and the ladder hint as a sentence ("'wait' 37 of 40 times: a rule could take this") |
| program | **Its program**: the command line, then each file the command names that resolves under the model folder, highlighted (bin/step.py); `-m ergostat.…` reads "ergostat's own: modelling rules" with the module's docstring and a Guide link, never an absolute .venv path; a daemon's command for `daemon:` blocks; `parse` regex |
| rule | **Its law**: the built-in's law in words and MathML from `block_fn` (onoff: "1 while located > 0 (located-worked off), until located ≤ 0"); expr: the expression with each named input as a link and its value now; lookup/schedule: the table; an implied block says which block's `goal:` implied it, linked |

Every rung shows **Its definition** after that: the block's YAML as written, highlighted, under `file.yaml:LINE` as a
link to /file. That is the universal "means", and the fallback when nothing above applies (an external block).

Then **Its place**: the goals and loops it serves (links that open the goal on the Diagram), what it commands or is
commanded by, the items it holds now (leases), and "show on Blocks" (`/diagram?view=blocks&sel=blk:NAME`). Then
**What it did**: the existing runs chart, Recent runs, cost and log tail, moved from the panel through the same
functions.

The address is `/agent/NAME`, and the open section can be named in the address (`#prompt`, `#program`).

## Gaps

1. `agent-spec-api`: /api/agents/NAME carries the specification. Server only. Incremental.
2. `agent-show-page`: the /agent/NAME page, by rung. Depends on 1. Incremental, the bulk of the work.
3. `agent-names-link-to-their-page`: every agent name in the UI links to the page, and Agents rows become links.
   Depends on 2. Quick.

No proposal gap is needed. The design above is the proposal, and the open choices (section order, rung table) are
settled here. A narrow-ai fixture is folded into gap 1's tests (a test model), and the decision rung uses
examples/docs-fresh, so no demo needs to change.
