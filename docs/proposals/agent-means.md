# What a narrow AI's specification and a decision's means of deciding are

Owner item 19 asks each agent's page to show, for a narrow AI, its **specification**, and for a decision, its
**means of deciding**. Today neither is declared anywhere: `narrow-ai` and `decision` are only an agent's `kind`
(`ergostat/spec/compile.py` `AGENT_KINDS`), checked against the blocks it may run (`KIND_RUNS`: a decision runs
`program` blocks, a narrow AI `ai` or `program` blocks). The one built-in narrow AI is an intent judge that names a
model (`Block.builtin_rung`, `spec/ir.py`). The ladder hint (`state.py`, `LADDER_MIN`/`LADDER_SHARE`) infers only
from what a controller decided (`state.decisions`, the `controller.decided` words with the numbers taken out). No
running demo shows either rung; `examples/docs-fresh` declares `picker: kind: decision`.

The proposal in one line: **nothing new is declared.** A narrow AI's specification is its block's contract as it
is written today. A decision's means is its block's program, plus, for item work, what it **may** decide (already
declared: `takes.to`) against what it **did** (the record). A controller decision has no closed answer set: the page
shows what it said and what of its commands was carried out, per `out` port, labelled apart.

## 1. A narrow AI's specification

**Settled:** the specification is the block as declared, read from the compiled block, in this order:

| Shown | From | Notes |
|---|---|---|
| what it is asked | `prompt` (text, or the file's text) | the whole prompt; a file is named and shown |
| what it works | `takes` (`kind`, `at` → `to`, `where`, `order`), `on`, `in` | the items or events that start it, and what it reads |
| what it may move | `out` ports, `actions`, `max`/`min` | its valves; nothing else changes the world (invariant 2) |
| what it may use | `tools`, `read`, `read-only`, `network`, `workdir`/`workspace` | section 12k's grants |
| what it costs and how long | the agent's `model` or the block's, `timeout`, the budget's `max-cost` (§9.9) | `max-cost` is the budget's, not a block key |
| how it is answered | `parse`, `goal`/`until` | |

The definition named `emits`. It is not a block key (compile.py has none), so what a block emits is read from the
record (the event types its runs wrote, counted), not shown as declared. Invariant 11 holds: declared and inferred
are kept apart and labelled.

**Rejected:**
- *A new `answer-schema:` or `examples:` key.* It would add a second contract beside `parse` and `takes.to` that
  nothing enforces at run time. A schema shown on the page but never checked is a guarantee wider than the code
  (lesson-8). If the owner wants one, it belongs with `parse` as a checked output contract, in a gap of its own.
- *The agent's own description as the spec.* An agent describes itself, never what it is used for (CONCEPTS §4),
  and one agent fills many blocks. So the spec is per block. An agent's page lists one spec per block it runs.

## 2. A decision's fixed answers

**Settled:** no `answers:` key. A decision block's fixed answers are already declared where the language puts them:

- **an item-taking decision** (an approver, a triage): `takes.to`, the states that count as done. `check` already
  refuses a state the kind lacks (`leases/compile.py`, `bad-states`), and `leases/dispatch.moved_on` already judges
  each run by it. `to: [approved, denied, deferred]` is the answer set.
- **a controller decision** (a picker) has **no closed answer set**. Its `out` ports say what it may command, not
  what it may decide: `page-picker`'s one port, `block.doc-writer`, takes any amount and any page. Its decision
  words are free text and never name a port (`examples/docs-fresh/pick.py:17,20`: "N stale, M changes/h: rewrite
  K, PAGE first", "few enough: wait"). They are filed under the goals the block serves, with the block as
  `source` and `{decision, why}` as data, no port (`spec/engine.py:2155-2158`).

So the means is: the block's program (`run`, or `daemon`); for item work, what it may decide (`takes.to`) and
what it decided; for a controller, what it may command (`out`), what it said (its grouped words) and what was
carried out. This is the default the definition gave, confirmed: nothing new is declared.

**Rejected:**
- *`answers: [approve, deny, defer]`, checked by `ergostat check` against decision lines.* For item work it repeats
  `takes.to` (two lists that can disagree). For controllers, decision words are free text that `state.decisions`
  already collapses ("12 waiting" → "# waiting"). A check would either refuse real lines, which means a new run-time
  refusal path, or pass anything, which is a denylist in disguise. It is also the wrong place: the kind lives on the
  agent, so `answers:` on a block whose agent is `ai` would mean nothing. It can be added later without breaking
  anything; removing it later could not. Leaving it out is the reversible choice.
- *The means as the program alone.* That hides the answer set the model already declares.

This agrees with SPEC §9.3, which gains no key, and with the ladder (CONCEPTS §4: a move down the ladder changes
one block's type and what it runs; the goal and the loop stay put). A rule's means is its built-in type and params.

## 3. What it decided against what it may decide; a ladder move as history

The agent page, one block at a time (no new panel: rows in the agent page the owner already decided on):

- **may / did, for item work** (`takes.to`). One row per declared state, with its count over the page's window:
  the `ergostat.lease.ended` acks, grouped by their `state` and joined by `run` to the `ergostat.lease.taken` that
  names the block. A declared state never reached shows **0**, not missing. An outcome outside the set (a nack back
  to `back`, a dead letter) is its own row, **"other"**, never folded into an answer. A `lease.ended` whose
  `lease.taken` is not found counts as **unattributed** and is shown, never dropped (lesson-3).
- **said / carried out, for a controller.** No 0 rows and no "other": there is no answer set to hold the words
  against. Two lists, labelled apart:
  - *what it said*: the `controller.decided` events whose `source` is the block, grouped with the numbers taken out
    as `state.decisions` groups them. A block serving two goals writes each line once per goal, so a word is
    counted once per run (`causedby`), not once per goal.
  - *what was carried out*, one row per `out` port, read from the record each kind of port leaves: a block port
    from the target's `block.commanded` events whose `data.from` is this block (`spec/engine.py:743, 990`); a flow
    port from `valve.opened` with this block as `source`; an auxiliary from `auxiliary.set`. A goal port (a
    setpoint) leaves no event, so it is shown as declared with "not recorded", not 0. The row is named "commands
    acted on", because a zero command, a command superseded while the target runs (only the latest starts it), and
    an advised command still waiting for approval leave no `block.commanded` (`pick.py`'s "wait" is never counted there). It is not a count of
    decisions and the page does not say it is.
- **The ladder hint** stays as it is (`state.py`) and is shown beside the "what it said" list it is read from. It
  reads `controller.decided` by goal name (`spec/legacy.py:76` keys controllers by goal), which is where a
  program's lines are filed, so the two read the same events.
- **A ladder move as the same block's history.** The model's versions (`ergostat/numbers/version.py`) already keep
  each version's blocks and agents. The page lists the block's rung per span of versions ("ai until v12, decision
  v13 to v20, rule since v21"), keyed by block name, and the counts above are split by span, so a rule's record
  never mixes with the decision it replaced. A block removed and made again under the same name shows the gap, and
  its old counts are not merged into the new one (lesson-5). Spans are ordered by version number, not by time
  (lesson-2).

**Rejected:**
- *A controller's `out` ports as its answers, its words matched to them, the rest "other"* (this proposal's first
  round). No word names a port, so on `page-picker` every decision would be "other" and `block.doc-writer` would
  always show 0: a table that is wrong on its own acceptance case.
- *A port named on each decision line* (a new `port` field). It is a new run-time contract for every controller's
  program, and the `{out, command}` line beside it already says which port. Reading the command records instead
  needs nothing new.
- *A rung timeline drawn as a chart.* The owner's rule is no new panels. The span list is text in the existing page.

## 4. The real cases for acceptance

- **narrow AI: `examples/alert-triage`.** Its `triage` block (`prompt: prompts/triage.md`,
  `takes: {kind: alert, at: new, to: [triaged, dismissed]}`) moves from `claude` (`ai`) to a new agent
  `triager: {kind: narrow-ai}`. The stand-in `run:` stays, so no AI is called. It is a real ladder move (a general
  agent's role narrowed) with a declared answer set.
- **a controller decision: `examples/docs-fresh`'s `page-picker`**, unchanged. It is already `kind: decision`,
  its stand-in already prints decision lines (`pick.py:17,20`) and commands `block.doc-writer`, which is advised
  (`mode: advise`). So "commands acted on" counts only the approved rewrites, while "what it said" counts every
  run: the case shows the two lists differ. No file in the example changes; the follow-up's acceptance runs it
  (it is not among the demos counted on :8791-:8797).
- **an item-taking decision: a fixture in `tests/`,** an approver on `kind: decision` with
  `to: [approved, denied, deferred]`. It seeds acks to two of the states, a nack and a dead letter, and covers the
  0 row, the "other" row and the unattributed count. It is a fixture and not a demo, because adding an approver role
  to a demo is designing that demo (invariant 3).
- *Rejected: the-job.* Its charter is that the owner alone decides (`me: kind: person`). Putting an AI triage or an
  approver there would change what that demo is about.

## 5. ergostat's own blocks

**Settled:** a built-in block (a judge, `onoff`, `limit` …) has no prompt or program the owner wrote. Its page names
the module that computes it and the first paragraph of that module's docstring, plus its declared params. The
intent judge with a model is the one narrow AI: its `judge`, `kinds`, `model`, `max-cost`, `threshold`. The source is
never shown. This is the default the definition credits to agent-spec-api; that gap is not on this clone's `main`, so
the follow-up reads `Block.builtin_rung` and `TYPE_KEYS` directly.

**Rejected:** *showing the source.* It is large and changes with every release. It also tells the owner how ergostat
works rather than what the block is.

## 6. Lines to change in the docs

- **SPEC §10, the agents table:** the `kind` row gains: "A narrow AI's page shows each of its blocks' contract (§9.3,
  §12k); a decision's shows its program and, for item work, its `takes.to` states against what it decided; for a
  controller, what it said and which of its commands were carried out (it has no closed answer set)".
- **SPEC §9.5, the `takes` row:** `to` gains: "for a decision, these are its answers, counted on its agent's page".
- **SPEC §9.3:** no new key, and a sentence saying so (an item-taking decision's answers are its `takes.to`; a
  controller's decision words are free text, and its `out` ports are what it may command, not an answer set).
- **docs/vocabulary.md, the comparison table:** a row that keeps the words apart. System dynamics' *decision rule*
  (a policy in a flow's equation) is ergostat's controller, filled at any rung, often a built-in on the rule rung.
  ergostat's *decision* is the rung (a short, fixed-answer call). They are not the same thing.
- NOTES.md's rung 3 ("a short model call with fixed answers") stays. It is now true of the declared `to`.

**A finding, outside this gap:** SPEC §9.9 does not charge runs whose agent is a `decision`, yet NOTES calls a
decision a model call. A decision block whose program calls a model is therefore spent unseen by the budget. That is
a fail-open on cost (lesson-3), and it belongs in a gap of its own, not in this one.

## The follow-up gap: `agent-page-narrow-ai-and-decision`

This amends that gap's (unwritten here) scope to the above: no new key, and the page reads what is declared.

- **Files:** `ergostat/agent_means.py` (new, small: a block's spec rows; may/did and said/carried-out counts; rung spans from versions),
  `ergostat/web/server.py` (the agent answer gains `spec`, `means`, `rungs` per block), `ergostat/web/static/pages.js`
  (rows in the agent page), `examples/alert-triage/ergostat.yaml` and `model/alerts.yaml` (the `triager` agent),
  `docs/SPEC.md`, `docs/vocabulary.md`. `examples/docs-fresh` is not changed (its decision lines are already there).
- **Tests:** `tests/test_agent_means.py` (the approver fixture: 0 row, other, unattributed, a same-name remake, spans
  by version; a controller fixture serving two goals: each word counted once per run, a zero command not counted as
  acted on, a goal port shown as not recorded), the browser file that covers the Agents page (both rungs shown),
  and `demo_check` on both examples.
- **Budget:** about 250 net lines of code outside tests and docs.
