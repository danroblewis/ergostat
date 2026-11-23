# agent-means-proposal: Proposal: what a narrow AI's specification and a decision agent's means of deciding are (docs/proposals/agent-means.md)

depends-on: []

Problem: owner item 19 asks the Agent page to show 'for narrow AI, its specification; for decisions, the means of deciding'. Nothing in ergostat declares either. narrow-ai and decision are only an agent machine's kind (ergostat/spec/compile.py:83, KIND_RUNS :114): a decision machine runs program blocks, a narrow AI runs ai or program blocks. The only built-in narrow AI is the intent judge with a model (spec/ir.py:737-743). The ladder hint (state.py:592-603) only infers that a decision or rule could fill a controller from what it decided (state.decisions, state.py:459-469). No demo has either rung (counted over /api/agents on :8791-:8797; examples/docs-fresh has picker: kind: decision).
Change: write docs/proposals/agent-means.md settling: (1) a narrow AI's specification: the prompt plus the block's contract (takes, out ports, emits, tools, read, actions, model, max-cost, timeout), or a new declared key (answer schema, examples); (2) whether a decision block declares its fixed answers (e.g. answers: [approve, deny, defer], checked by `ergostat check` against its decision lines and counted per answer) or the means is only its program plus observed decisions; which agrees with SPEC §9.3 and the ladder (docs/CONCEPTS.md:165). Default until the proposal says otherwise, no owner question: nothing new is declared; the means is the block's program plus what it decided; (3) how the page shows 'what it decided' against 'what it may decide', and a ladder move (decision to rule) as the same block's history; (4) which demo or fixture gets a narrow-ai and a decision agent (e.g. the-job's triage; an approver) so acceptance has real cases; (5) ergostat's own module sources: named with their docstring, not shown (the default agent-spec-api builds); (6) the SPEC and docs/vocabulary.md lines to change. It confirms or amends agent-page-narrow-ai-and-decision. (R12 piece 5's 'decide on Agents' is already decided by the owner: Agents stays as the index and each agent gets a page.)
Definition of done:
1. The proposal answers 1-6 with the alternatives rejected and why.
2. It names the follow-up gap with file list and budget.
Files: docs/proposals/agent-means.md.
Acceptance tests: review only.
Budget: about 150 lines, no code.

Milestone: agent-show-page. Owner items: 19 (narrow AI's specification; a decision's means of deciding). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Round 3: the proposal is written, and both round-2 findings are answered. A controller has no closed answer set, so
its page shows its grouped words and the commands acted on, read from `block.commanded`/`valve.opened`.
`examples/docs-fresh` is not changed, because `pick.py` already prints decision lines. The proposal also says that a
target with two commanders is shown as shared and not credited to one of them, because `data.from` names only the
last commander read. Nothing is left in this gap; the follow-up `agent-page-narrow-ai-and-decision` is scoped at the
proposal's end.
Overrun reason: the proposal is 170 lines, not about 150, because the round-2 findings required each controller-record source and its limits to be stated with file references; there is no code.
