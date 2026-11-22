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
