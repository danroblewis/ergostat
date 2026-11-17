# Decisions and corrections

A long working session stays coherent because it remembers what the owner decided, and stops making a mistake
once the owner has corrected it. A fresh session remembers neither. In ergostat both are kept in the record, as
items: an **`ergostat.decision`** is a choice the owner made that should hold for later work, with the owner's
words, its reasons and the alternatives rejected; an **`ergostat.correction`** is the owner telling the work it
was wrong, in their words, with the kind of work it applies to. Each is proposed (by an extractor reading
session transcripts, by a block, or by a person), and only the owner confirms it. The confirmed ones are given to
every new session at its start, as Markdown, within a size budget. The format is in `docs/SPEC.md` §5a
(`ergostat help spec`); this page is how to use it.

| Your question | Where |
|---|---|
| [How do decisions get in?](#proposing-them) | `ergostat decisions extract`, a block, `ergostat decisions propose` |
| [How do I confirm or reject one?](#answering-them) | an item's page (Items → `ergostat.decision`), `ergostat decisions confirm` |
| [How does a session start from them?](#starting-a-session-from-them) | `ergostat context decisions`, `ergostat context corrections`, MCP `context` |
| [What if a correction is given twice?](#a-correction-given-twice) | needs attention, `correction-repeated` |
| [How is it modelled and measured?](#modelling-it) | stocks counted from the items, flows of their moves |

## Proposing them

**From transcripts.** `ergostat decisions extract FILE|DIR|ITEM` reads Claude Code transcripts (a session's
`.jsonl`, every one in a folder, or a session item whose transcript the record already holds as `claude.*`
events) and proposes the decisions and corrections in the owner's turns. Only what the owner typed is read: tool
results, the harness's notes and the reminders it inserts are left out. Each proposal quotes the owner's words
verbatim, with the session, the line and the time.

```sh
ergostat decisions extract ~/.claude/projects/my-project/                 # the stand-in: no model, no tokens
ergostat decisions extract session.jsonl --model sonnet --max-cost 2      # the AI extractor, stopped before $2
ergostat decisions extract session.jsonl --since 4000                     # from line 4000 (or 2026-11-16T09:00, or 2d)
```

There are two extractors. The **stand-in** is heuristics on the owner's sentences: one that pushes back ("no,
not like that", "you keep", "why did you") is a correction of the assistant's turn before it, joined with the
directive that follows it; one that states a rule or a choice ("we decided", "never", "always", "let's",
"instead of") is a decision. It is free and fast, and its proposals are many and rough (confidence 0.3): it is
for tests, examples, and a first look. The **AI extractor** (`--model`) gives a model the owner's turns with the
assistant's turns around them, a batch at a time (about 6,000 tokens), with the decisions and corrections already
found so that a repeat or a supersession can name them. Its answers are checked, not trusted: every quote must
be found in an owner's turn (whitespace aside), and takes its line from where it was found; a finding with no
quote found is dropped and counted. It stops before its cost cap would be passed, and reports calls, tokens and
cost (`extractor.ran`).

Running again proposes nothing new: an id is a slug of the sentence, so the same decision is the same item; a
known decision found again with new words has them appended (`ergostat.decision.seen`), never replacing the
first.

**As a block.** The extractor is an ordinary block. `--print` gives its proposals as event lines for the engine
to record, from the block; `--new` reads only what each transcript gained since the block's last run:

```yaml
blocks:
  extractor:                      # the stand-in, hourly
    type: program
    run: ergostat decisions extract run/sessions --new --print
    every: 1h
  extractor-ai:                   # the AI mode: the block's prompt is the extractor's instructions
    type: ai
    prompt: prompts/extractor.md  # improvable like any ai block's prompt
    run: ergostat decisions extract run/sessions --new --print --model sonnet --max-cost 1 --prompt -
    every: 6h
```

With `--prompt -` the extractor reads the block's prompt from standard input (the engine's footer and inputs
taken off) and uses it in place of its own instructions; the answer's form is always the extractor's.
Without it, the instructions are ergostat's (`ergostat/decisions/prompt.md`).

A block, or any program, may also print a proposal itself:

```json
{"event": "ergostat.decision.proposed", "data": {"decision": "Items are folds of events.",
  "words": [{"text": "every item is a fold of its events", "session": "s1", "line": 120}],
  "reasons": ["history for free"], "alternatives": [{"option": "a table per kind", "why": "loses history"}],
  "scope": ["items"]}}
```

It is checked like any proposal (the sentence, the owner's words with where they were said) and refused with
why when it does not hold. A block may never confirm, dismiss, supersede or retire: those are the owner's.

**By hand.** `ergostat decisions propose "SENTENCE" [--words W --session S --line N] [--reason R]
[--rejected "OPTION: WHY"] [--scope X] [--supersedes ID]`, and `ergostat corrections propose "SENTENCE"
--kind ui [--corrects ...]`. The owner proposing needs no quote: their sentence is their words. MCP
`record_event` with `ergostat.decision.proposed` or `ergostat.correction.proposed` does the same.

**From the record.** `ergostat corrections scan` proposes the corrections the record already holds: the
owner's dismissals with a reason, items moved back to an earlier state with a reason, and `ergostat.message`
events classed as corrections.

## Answering them

Everything proposed waits for the owner. On the Items page, `ergostat.decision` (or `ergostat.correction`)
lists them by state; an item's page shows the decision, the owner's words with where they were said, its
reasons, what was rejected and who proposed it, and the answers:

- **Confirm** (a proposed one), with a reason if you like: from now on it is in every session's context.
- **Dismiss** (a proposed one), with a reason, required: it is what the next proposal learns from.
- **Supersede** (a confirmed decision), with a reason and the decision that replaces it, both required.
  A decision is never superseded by implication: one proposed with `supersedes` leaves the old one in force
  until the owner says so.
- **Retire** (a confirmed correction that no longer applies), with a reason.

The same from the command line: `ergostat decisions list --state proposed`, `ergostat decisions confirm ID
[--reason]`, `dismiss ID --reason`, `supersede ID --by ID --reason`; `ergostat corrections confirm | dismiss |
retire`. An id may be given whole or as its slug.

## Starting a session from them

```sh
ergostat context decisions --scope ui --budget 1500t > ctx-decisions.md
ergostat context corrections --kind testing > ctx-corrections.md
```

Each renders the confirmed items as Markdown, most relevant to the scope (or kind of work) first, as many in full
as fit the budget (the sentence, the owner's words and where they were said, reasons, rejected alternatives,
scope, id), then one-line pointers, then a count of the rest. `--proposed` adds the ones still waiting, marked
so. MCP `context` gives the same to an agent. A file it writes is a starting context anywhere: an `ai` block's
prompt, a parity benchmark variant (`ergostat bench parity run --variant decisions=ctx-decisions.md`).

## A correction given twice

A correction that makes the same point as an earlier one (most of the owner's content words shared, for the same
kind of work) is linked to the first (`repeats`, and `repeat: true`, for a sensor to count), and the first lists it
(`repeated_by`). The repeat is raised as a
finding, `correction-repeated` ("correction X: given 2 times"), under needs attention, while the repeat waits for
the owner or the first is confirmed: the first correction did not change what was done. The corrections context
says how many times each was given.

## Modelling it

The items are the record of the function, and counting them makes it a system like any other:

```yaml
stocks:
  decisions-proposed:   {sensor: {items: ergostat.decision, state: proposed}}
  decisions-confirmed:  {sensor: {items: ergostat.decision, state: confirmed}}
  corrections-proposed: {sensor: {items: ergostat.correction, state: proposed}}
  corrections-active:   {sensor: {items: ergostat.correction, state: confirmed}}
flows:
  decisions-confirming:  {from: decisions-proposed, to: decisions-confirmed,
                          sensor: {items: ergostat.decision, entering: confirmed}}
  decisions-superseded:  {from: decisions-confirmed, sensor: {items: ergostat.decision, entering: superseded}}
  corrections-confirming: {from: corrections-proposed, to: corrections-active,
                           sensor: {items: ergostat.correction, entering: confirmed}}
  corrections-retired:   {from: corrections-active, sensor: {items: ergostat.correction, entering: retired}}
  corrections-repeated:  {to: corrections-proposed,
                          sensor: {items: ergostat.correction, entering: proposed, where: {repeat: true}}}
```

What to hold near zero is corrections repeated, and decisions the owner had to restate ("we already decided
this"). The parity benchmark (`docs/parity-bench.md`) measures what the decisions context is worth to a fresh
session against the other starting contexts.
