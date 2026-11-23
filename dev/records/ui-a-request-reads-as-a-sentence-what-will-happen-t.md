# ui-a-request-reads-as-a-sentence-what-will-happen-t: A request reads as a sentence: what will happen, to what, who asks and why

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q44 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list; action and request item pages

**The problem:** Entries read 'person/approve@3156 approve is asked: Outward acts wait for your approval. `ergostat actions` lists them (and the p...', cut off; an action's first line is 'ran jira-transition, class jira-transition, gate approve' with the plain description buried in Fields; 'modelling holds no-unit on stock.api-q0 … the decision tier has no certain change for it'.

**The change:** First line from fields the entry already has: '{description} {target}, for {item}, asked by {block} because {why}', for example 'Move SCRUM-7 to Done in Jira, for ticket/SCRUM-7, asked by close'. Person asks print in full (a <details> for anything past three lines). The exact command sits in a collapsed <details>. A modelling request reads 'api-q0 has no unit: modelling cannot decide one. Deny tells it to stop asking; the unit is yours to set through the Supervisor.'

**User stories it serves:** E2, A4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8792/ no entry under 'Waiting for you' contains '...' or a backtick; each has a first line ending before any 'python3'; the command is inside a closed <details>; every Deny-only entry contains a sentence starting 'Deny '.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. About 26 net lines of code outside tests (entries.py, state.py, diagram.js, pages.js, style.css).

- Side list (/diagram): each entry waiting on the owner (`[data-inbox]`) now starts with its sentence, linked to its
  page, then "waiting N". Its text is shown in full, with anything past three lines in a closed `<details>`, and the
  exact command (the action's own `run`, then the `ergostat inbox` line) is in a closed `<details class="cmd">`.
  Backticks are drawn as `<code>`. An action reads `{description} ({arg value, ...}), for {item}, asked by {block}
  because {why}`. A person block reads `{name} asks: {ask}`, uncut. A held modelling request reads `{check's words}.
  Modelling cannot decide it: {why}.`, then `Approve hands it back to modelling's AI tier.` when approvable, then
  `Deny tells it to stop asking until {part} changes; the change is yours to make through the Supervisor.` Step-test
  and change entries are no longer cut with '...' either.
- Action item page: its sentence (`.action-says`) comes first, then the old state/class/gate line. The command is in
  a closed `<details>`, both on its own page and in the list of actions about an item.
- Choices taken without anyone to ask (the reversible ones):
  - 'Waiting for you' is taken to mean the inbox entries in the side list's *Needs attention*. No heading was renamed.
  - The request's sentence is one generic sentence for every code, not a no-unit special.
  - The request item page is left as it was: its fields already read in full there.
  - The new `summary` is shared, so `ergostat inbox`, the status and notifications say the same sentence.
    `tests/test_inbox.py`'s notification check was updated to the new wording.
- Tests: the acceptance is `tests/test_inbox_page.py::test_a_request_reads_as_a_sentence_with_its_command_folded` and
  `::test_a_deny_only_modelling_request_says_what_deny_does`. It runs on a free port, not :8792: that demo is not in
  this container. Each test was seen to fail under these breaks: backticks left raw; the command box open; "Deny"
  reworded; the item page's first line reverted to the action name.

Round 2: the review's one finding answered. About 29 net lines of code outside tests in all (round 2 added 3).

- Finding (blocking): round 1's side-list entries dropped each class's record and its suggestion up the ladder
  (SPEC §12o). Fixed. `state.attention` passes `record` and `suggest` into each inbox entry again (state.py), and
  `inboxBody` draws them on a muted line of their own (`.ladder`), below the sentence and outside the folded command
  (diagram.js). The wording is `stats.record_said` and `stats.suggest`, unchanged.
- Test: `tests/test_inbox_page.py::test_an_entry_keeps_its_class_record_and_its_suggestion_up_the_ladder`. The owner
  approves `push` six times, one more is held, and the entry must show "7 asked this week, 6 approved, 0 denied" and
  "consider gate: auto". It also checks that the entry still passes the acceptance. Seen to fail under two breaks:
  the `.ladder` line not drawn, and `suggest` dropped on the server while the record still shows.
- Run: `tests/test_inbox_page.py` (4 passed, under the watchdog, with Playwright), `tests/test_inbox.py` (30 passed),
  ruff clean. Not run here: the unit suite and the four browser files, which the merge queue runs. `main` has no
  commits the branch lacks, so there was nothing to merge.

Round 3: both findings of review 2 answered (both blocking; it raised no others). About 28 net lines of code outside
tests in all (round 3 subtracted 1).

- Finding 1 (the command gone from the CLI and notifications): `ergostat inbox` prints a `runs: {command}` line under
  each action again (cli/inbox.py), and a `detail: full` notification carries `runs: {command}`, scrubbed like the
  summary (deliver.py). A `minimal` message still leaves it out, as on main. The status line (`says` in
  `state.attention`) carries it as well. `tests/test_inbox.py:373` checks the full message for the `runs:` line again.
- Finding 2 (the reason said twice): the shared `summary` no longer holds the reason. It reads `{description}
  ({args}), for {item}, asked by {block}`, and `why` is unchanged from main, so the CLI, notifications and the status
  each say it once. The side list's first line adds `because {why}` itself (state.attention's `first`), and then
  drops `more` so the reason is not shown again. When the action has a warning, the reason stays on its own line, as
  before. Choice taken (reversible): the reason is left out of the shared summary rather than clearing `why`, because
  `why` is read as its own field (tests/test_inbox.py's impact test, the CLI's `why:` line).
- Test: `tests/test_inbox.py::test_an_action_says_its_command_and_its_reason_once_in_the_cli_the_message_and_the_status`.
  An action whose item has an impact and a test result must show the reason exactly once and the command, in the CLI
  listing, in a full-detail message (its model names scrubbed: `echo flow-1 >> flow-1.txt`) and in the status
  line. The page's first line must end `because {why}`. Seen to fail under three breaks: the CLI's `runs:` line
  removed; the message's `runs:` line removed (the old message test fails too); and the reason put back into the summary
  (the count is 2).
- Run: `tests/test_inbox.py` (31 passed), `tests/test_inbox_page.py` (4 passed, under the watchdog, with Playwright),
  ruff clean. Not run here: the unit suite and the four browser files, which the merge queue runs. `main` has no
  commits the branch lacks.

Round 4: main (720426bd) merged in. Its conflicts in diagram.js and style.css are resolved, keeping both sides. About
29 net lines of code outside tests in all (round 4 added 1, a CSS rule).

- The conflict: main split the side list into three headed groups ('Waiting for you', 'Goals off', 'Model
  housekeeping'), and each entry now starts with a state word. Each inbox entry keeps main's word (`waiting · `,
  `request · `) as its first element, then this gap's sentence, ladder line and folded command. A CSS rule
  (`.att-word + .ask-first`) keeps the word and the sentence on one line.
- A clash found by main's test: the branch's `waiting` field (the entry's age, as text) had the same name as main's
  `waiting` flag (it waits on a person). So held modelling requests were sorted under 'Waiting for you'. The age is now
  `age` (state.py, diagram.js).
- Two tests updated to fit both changes:
  - `tests/test_diagram_rendering.py::test_needs_attention_is_three_headed_groups_in_a_fixed_order` found held requests
    by the text `request/` in the row. That is the id, which this gap replaces with the sentence. It now finds them by
    their `request · ` word and checks each says 'Modelling cannot decide it'. It was seen to fail before the rename
    (3 rows under 'Waiting for you').
  - `tests/test_inbox_page.py`'s `waiting_entries` now waits for the entries to be in the page, not visible, because
    held requests sit in the folded housekeeping group.
- Choice taken (reversible): the acceptance names 'Waiting for you'. With main's groups, a Deny-only modelling request
  sits under 'Model housekeeping', not there. The acceptance checks are run on every `[data-inbox]` entry wherever it
  sits, so the Deny sentence is still checked.
- Run: `tests/test_inbox_page.py` and the grouping test (5 passed), `tests/test_items_page.py` (23 passed), both under
  the watchdog with Playwright; `tests/test_inbox.py` (32 passed); ruff clean. Not run here: the unit suite and the
  rest of the four browser files, which the merge queue runs.

Round 5: main (d1bfd1a0) merged in. Its conflicts in diagram.js and pages.js are resolved, keeping both sides. No net
lines of code were added in this round.

- diagram.js: main added `goalButton`/`showGoal` (a goal's name in the side list opens its evidence). They sit beside
  this gap's `inboxBody`. In the side list's row, an entry waiting on the owner still draws its sentence
  (`inboxBody`). Any other entry draws main's goal button when its `what` is `loop {name}`.
- pages.js (the list of actions about an item): main's muted line is kept (`gate`, `asked by`, who approved it), and
  this gap's folded `commandBox` replaces main's open `<pre>`.
- Run: `tests/test_inbox_page.py` (4 passed), `tests/test_items_page.py` (25 passed), and from
  `tests/test_diagram_rendering.py` the grouping test (1 passed) and main's goal-name test (2 passed). All four were
  run under the watchdog with Playwright. Also run: `tests/test_inbox.py` (32 passed); ruff clean. The whole of
  `tests/test_diagram_rendering.py` ran past this session's 10-minute limit for one command and was stopped. It was not
  seen to pass here. That file, the unit suite and the rest of the four browser files are left to the merge queue.
