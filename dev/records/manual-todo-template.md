# manual-todo-template: a person's own to-dos, with instructions, grouped by where they must be done

The owner, 2026-11-22: "a list of ToDo items I am supposed to do manually and providing clear accurate instructions ... At times, I have to do certain tasks on a bastion host or on a different VPN, and I would like those to be grouped together ... I am regularly pinged about from stakeholders, and I want to be able to track and explain their progress in a reliable and consistent way."

Change: a library template `todo` (`ergostat/library/templates/todo/`), generic and with no organisation's names:
- An item kind with states such as new, ready, in-progress, waiting, done, dropped. Fields: title, requester or stakeholder, **where** (the access context: a named host, bastion, VPN or "anywhere"), instructions (ordered steps, with commands and how to check each worked), due, waits on (another item, a person or an external thing), and notes.
- **Batches:** ready to-dos grouped by `where`, so everything for one bastion or VPN is done in one sitting, with its instructions in order.
- **A stakeholder update:** `ergostat why` on a to-do gives a consistent status, what it waits on and what happens next, from the record.
- Adding one from the command line or through an agent is one step; a person's "done" is recorded through the inbox's existing `--done`.

Definition of done: a demo under `examples/` with to-dos across three access contexts; tests for grouping, waiting, the status text, and that the template adds no action that writes to any outside system.

## Where it stopped

Built (round 1), 452 net lines outside tests, docs and dev (budget 600):

- `ergostat/library/templates/todo/template.yaml`: the kind `${kind}` (new, ready, in-progress, waiting, done,
  dropped; title, requester, where, instructions as `[text | {do, run, check}]`, due, waits_on, notes), a
  `${wait-kind}` for what someone else does (asked, answered) and a `${batch-kind}` (open, clear); stocks new,
  ready, waiting, done; two person blocks (`write-up` for new ones, `do` for ready ones) on goals held at 0; the
  batcher, a program on the rule rung. No action, workspace or daemon; an optional `command` is the owner's own
  source, read by `collect`.
- `ergostat/library/run/todo.py` (`todo batches`): frees a waiting to-do once everything its `waits_on` names is
  finished (declared finished only; an id never recorded keeps it waiting), then one batch item a place, its
  to-dos the earliest due first, every one's instructions in order in `sitting`; says a batch only when it
  changed, and clears an emptied one. It reads the record and prints lines.
- Three generic changes the template needs, each in SPEC §5a: an item kind's own `finished:` (a template cannot
  write `messages: done:`, and without it every never-left `ready` read as finished); `moves-from:` (exposes the
  fold's existing `moves_from`, so the batcher's `todo.freed` moves a to-do only out of waiting: a drop recorded
  between its read and its write stays a drop, lesson 1); and in `why` a `person` root: with no block taking the
  item, a person block whose goal counts every item of its kind in that state (no `where:`) is the cause, the next
  step the first of the kind's `on:` events, as written, out of the counted states, as the `ergostat event --add`
  that records it.
- Demo `examples/todo-list/` (bastion-1, lab-vpn, build-host and anywhere); tests in `tests/test_todo_template.py`.
  Each new test was seen to fail with the code it guards broken (the person root, the kind's finished states, the
  all-waits check, the due order, the batch key's hash, `moves-from:`, the `where:` exclusion).

Readings taken, with nobody to ask, the most reversible chosen:

- "A person's done is recorded through the inbox's existing `--done`": the inbox answers a person block's ask
  (`ergostat inbox person/todo-do --done N`), which records how many they did along `flow.todo-doing`. It names no
  item, so each to-do is moved by its own event (`ergostat event --add todo.done --item todo/ID`, or MCP's
  `record_event`), one step, as `why` says. Making `--done` move a named to-do would change the inbox for every
  person block, so it was left out.
- Waiting on a person or an outside thing is an item of `${wait-kind}`, linked by `waits_on`, so `why` follows it
  as it follows another to-do.

Not run here: `scripts/demo_check.py` on the new demo was refused in this session (`uv run python
scripts/suite_watch.py -- uv run python scripts/demo_check.py --seconds 25 todo-list`). In its place
`test_the_demo_batches_its_todos_across_three_places` runs the demo's own compiled collector and batcher commands
on a copy. No page changed, so no browser file was run. The unit suite was not run whole (that is the factory's
step). Run one file at a time, all passing: test_todo_template, test_templates, test_why, test_finished_states,
test_footprint, test_library_trust, test_library_provenance, test_library_tree, test_library_untrusted; ruff clean.
Main had not moved since the branch began (nothing to merge).

Round 2 (the review's two blocking findings; it raised no others):

- A dropped prerequisite no longer frees its to-do. The batcher takes `--met done,answered`, which the template
  passes. It is required, so a call without it is refused instead of guessed. A wait is over only when everything
  it names is in a met state. A to-do whose prerequisite ended any other way (dropped) stays waiting. The batcher
  says why once, in the to-do's `stuck` field (event `todo.stuck`, no move; shown on the Items tab; cleared when the
  to-do is freed). Test: `test_a_todo_whose_prerequisite_was_dropped_stays_waiting_and_says_why`.
- A to-do waiting again is not freed by its old wait. Only the `waits_on` ids named by the event that last moved it
  into waiting, or by an event after it, count. That event is found by its id among the to-do's events in seq
  order, not by time. If the move cannot be found (rolled up), the to-do stays waiting and `stuck` says so. The
  fold is unchanged (waits_on still folds as a relation), the most reversible choice, since the generic fold and
  every other kind stay as they are; so `why` still lists the old link, skipped as finished. Test:
  `test_a_todo_waiting_again_is_not_freed_by_the_wait_it_had_before`.
- Both new tests failed with the code they guard broken (freeing on any declared finished state; counting every
  `waits_on` id). Run one file at a time, all passing: test_todo_template, test_templates, test_library_trust,
  test_why, test_finished_states; ruff clean. demo_check, the whole unit suite and the browser files were not run
  here (no page changed). Main has not moved since the round-1 merge.

Round 3 (the review's one finding, blocking: `why` on a waiting to-do with nothing unfinished to wait on):

- `why` now says it. In the `work` root (a working state no block takes from: `ergostat/why/blocks.py`), for a kind
  with precedence relations, it says that what the to-do waits on is finished (the ids named), or that it waits on
  nothing recorded. It also gives the item's own `stuck` text when one is recorded. The next step is the first of the
  kind's `on:` events in the order written, as with the `person` root. Events into the current state, back to the
  kind's first state (`todo.added`, which re-adds it) and barred by `moves-from:` are left out. The step is given as
  the `ergostat event --add` that records it (before, the work root had no command). For a waiting to-do that is
  `todo.ready`, never `todo.added`, and not the batcher's `todo.freed`, which comes last as written. The `stuck` field
  is read generically (any kind's item may carry one). SPEC §5a says so.
- The batcher now also sets `stuck` when a waiting to-do's wait names nothing: nothing named by the move into
  waiting or since. That covers the note-only re-wait and a to-do waiting on nothing named. Before, neither said
  anything. Its text tells the person to record `todo.waiting` with a `waits_on`, or `todo.ready`.
- Tests: the dropped-prerequisite and waiting-again tests now check the summary's stuck text and the next step
  (owner `whoever records todo.ready`, command `ergostat event --add todo.ready --item ...`, no `todo.added`). A new
  test, `test_a_todo_waiting_on_nothing_named_says_so_and_what_happens_next`, covers the nothing-named case. Each was
  seen to fail with the code it guards broken: no stuck text in `why` (3 failed), the old sorted next step that
  includes the first state (3 failed), and the batcher not saying stuck for a wait naming nothing (2 failed).
- Run one file at a time: test_todo_template (14 passed), then it with test_why and test_finished_states (52
  passed); ruff clean. tests/test_items_page.py under the watchdog: 56 passed and 2 failed, the same two in both
  runs: `test_actions_say_per_class_asked_approved_denied_and_whether_held` and
  `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` (a Playwright wait timing out). Both read
  the Actions class lines and the header's goal counts. Neither reads `why`, an item's `stuck` field or the to-do
  template, so I take them to be unrelated. I could not confirm that on the previous code: putting the old two
  source files back for one run was refused (`git checkout HEAD~1 -- ergostat/why/blocks.py
  ergostat/library/run/todo.py`). demo_check and the whole unit suite were not run here. Main has not moved since
  the round-1 merge. 518 net lines outside tests, docs and dev (budget 600).

Round 4 (the queue's one finding: `tests/test_changesets.py::test_every_examples_items_fold_as_they_did_where_no_rules_were_added[todo-list]` failed alone):

- Cause: the test allowed a refused event only of a final state (form `final`). The todo kind's `moves-from:` (this
  gap's generic change, SPEC §5a) refuses a state move out of any other state (form `from`), and the test's random
  events hit it. The fields still fold latest-wins, which is what the test checks. The fold is right; the test did
  not know the rule. It now allows a `from` refusal only for an event type the kind's `moves_from` names, and a
  `final` one only for a kind with final states, so any other refusal still fails it. With the old assertion it
  fails (as the queue saw); with the new one it passes. Only the test changed (3 lines), no code.
- Run one file at a time: test_changesets (60 passed), test_todo_template (14), test_item_systems (7),
  test_modelling_core (24), test_rollup (52), and the other files that run over every example: test_architecture
  (9), test_blockdiagram (71), test_chains (32), test_cli_fallback (18), test_cloud_arrivals (34), test_daemon_docs
  (29), test_daemon_yaml_review (33), test_extremes_closed (14), test_scale_caches (37); all passed; ruff clean.
  demo_check, the whole unit suite and the browser files were not run. Main has not moved (merge base is main).

Round 5 (the review's one finding, blocking: lesson 1 in the batcher's freeing. A new `todo.waiting` recorded
between its read and its write, with no move or out to ready and back, was still freed, since `moves-from:` checks
only the state):

- The batcher's write is no longer something the fold can take on trust. The batcher prints its line and the
  engine records it later, so no lock can be held across that write. The guard therefore sits in the fold, as a
  compare-and-set on the item's version. A kind's new `if-unchanged:` (SPEC §5a, generic and opt-in: a kind without
  it folds as before) lists the event types written from a reading of the item. Each must carry `read`, the item's
  count of events when it was read. It applies (fields and move; `read` is not kept as a field) only when the item
  has had no event since. The count is taken in the record's order, not by time (lesson 2). If the count differs,
  or `read` is missing or not a whole number, nothing applies (fails closed, lesson 3). It is said in `refused`,
  form `read`, and still counted among the item's events (test_rollup checks that count against the record).
- The template sets `if-unchanged: [todo.freed, todo.stuck]`. The batcher folds each waiting to-do from the very
  events it queried and judges that fold, not the index's copy, so the count it stamps is the count of what it
  judged. `moves-from:` stays as a second guard for a freeing written by hand.
- Also: compile.py (`bad-if-unchanged`), the item index's kinds key, and library/trust.py's allowlist of item keys.
  `tests/test_changesets.py`'s example-wide fold test leaves an `if-unchanged:` event type out of its random events,
  since one with no `read` is refused whole by design and is tested here instead.
- Tests: `test_a_todo_waiting_on_something_new_while_the_batcher_frees_it_stays_waiting` (both cases of the
  finding: the new wait with no move, and ready then waiting again; then freed once the new one is done),
  `test_a_new_wait_between_the_batchers_list_and_its_reading_is_judged_on` (monkeypatched into the batcher, after its
  listing and before its query), `test_an_event_written_from_a_reading_is_refused_without_the_count_it_read`, and
  the drop race test now expects the `read` refusal and checks `moves-from:` alone. Seen to fail with the code
  broken: without the count comparison in the fold, 3 failed; with the batcher judging the index's copy, the
  between-the-list test failed.
- Run one file at a time: test_todo_template (17 passed), test_changesets (60), test_rollup (52), test_why (33),
  test_finished_states (5), test_templates (37), test_item_systems (7), test_modelling_core (24),
  test_library_trust (49), test_library_untrusted (22), test_scale_caches (37); ruff clean. demo_check, the whole
  unit suite and the browser files were not run (no page changed). Main has not moved. 545 net lines outside tests,
  docs and dev (budget 600).

Round 6 (the queue's one finding: conflicts with main in `ergostat/spec/compile.py` and `ergostat/spec/ir.py`):

- Main (8a27f9e3) merged in. Both conflicts were main's new item-kind key `attention:` sitting next to this branch's
  `finished:`, `moves-from:` and `if-unchanged:`. Both sides were kept: in `ITEM_KEYS`, in the kind's checks (the
  branch's three, then main's `attention`), in the `ItemKind(...)` call and in the `ItemKind` dataclass fields. No
  code changed besides the merge.
- Run one file at a time after the merge: test_todo_template, test_templates, test_library_trust (103 passed),
  test_finding_attention, test_changesets, test_why (96 passed), test_finished_states, test_rollup,
  test_item_systems (64 passed); ruff clean. demo_check, the whole unit suite and the browser files were not run.
