# The parity benchmark

How much of a long session's knowledge does a fresh session recover from a given starting context? This is F3 of
[the harness parity plan](proposals/harness-parity-plan.md): the measure every later item is scored by. Each
starting context (a *variant*) is plain text, so any projection can be measured: the built-ins below, a file
written by hand, or `ergostat context RECIPE > FILE` once projection recipes land (decisions and corrections, 2.10,
2.12, 2.13).

## What it runs

- **Cases** (JSON lines): a question only the long session could answer, or a small task it did, with the ground
  truth in the owner's words and the transcript lines it came from. Kinds: `decision` (what was decided, and
  why), `meaning` (what the owner means by a phrase), `rejected`, `preference` (a rule of the owner's), `state`
  (the state of something at a point), `task` (judged against the owner's later correction).

  ```json
  {"id": "button-colour", "kind": "preference", "question": "What colour does the owner want the buttons?",
   "truth": "make them green, never red", "source": "line 3", "rubric": "green; not red",
   "checks": {"all": ["green"], "none": ["\\bred\\b"]}, "tools": []}
  ```

  `checks` are exact (case-insensitive patterns the answer must, may or must not contain: `all`, `any`, `none`),
  reported beside the judge's verdict. `tools` names read-only tools a case needs (`Read`, `Grep`, `Glob`, reading
  `--repo`); by default a session has none.
- **A fresh session per case and variant**: `claude -p --model sonnet` with `--safe-mode` (no CLAUDE.md, skills,
  hooks or settings of its own), no MCP servers, no saved session, in an empty directory. The context is its system
  prompt, after a fixed preamble the same for every variant, so the cases of one variant read it from the prompt
  cache; the case is its message.
- **A judge**, a separate sonnet session, given the question, the ground truth, the rubric and the answer (never the
  variant's name), says `correct`, `partly`, `wrong` (including "I don't know") or `contradicts` (asserts what the
  owner rejected, or makes the mistake the owner corrected), with a one-line reason.
- **The scorecard** (`scorecard.md`, `scorecard.json`): per variant (score: correct 1, partly ½, the rest 0;
  counts of each verdict; exact checks passed; dollars; tokens in and out; the context's size), per kind, per case,
  and the cases each variant did not get right, with the judge's reason. Every answer is kept in `answers.jsonl` as
  it comes: a run again on the same directory runs only what is missing (a new variant, a changed context or case,
  an answer that failed), and `--max-usd` stops starting cases once that much is spent, counting what the
  directory already holds.

## How to run it

```sh
# the built-in starting contexts, each to a file
ergostat bench parity context none   > ctx/a-none.txt
ergostat bench parity context docs   --repo .                    > ctx/b-docs.txt
ergostat bench parity context owner  --transcript SESSION.jsonl  > ctx/c-owner.txt    # the owner's messages, most recent first, to --budget characters
ergostat bench parity context fork   --transcript SESSION.jsonl  > ctx/d-fork.txt     # the last turns that fit --budget (or --last N)
ergostat bench parity context memory --dir ~/.claude/projects/PROJECT/memory > ctx/e-memory.txt
# (f) later: ergostat context decisions > ctx/f-decisions.txt

# draft cases from a transcript (an AI pass over the owner's messages; each quote checked against its lines)
ergostat bench parity draft --transcript SESSION.jsonl --out drafted.jsonl
# ... read and prune them into cases.jsonl, then:
ergostat bench parity run --cases cases.jsonl --out results \
  --variant none --variant docs=ctx/b-docs.txt --variant owner=ctx/c-owner.txt \
  --variant fork=ctx/d-fork.txt --variant memory=ctx/e-memory.txt --max-usd 8
```

`ERGOSTAT_AI` names another command in place of `claude` (the tests use a stand-in).

## Privacy

A real dataset is the owner's conversation: the transcript, the cases, the contexts made from it, the answers and
the scorecards stay outside the repository. The repository holds the harness and tests on made-up data
(`tests/test_parity.py`).
