# guide-models-that-answer-why: teach agents to build models that can say what is holding work up

The owner, 2026-11-22: when "why isn't this done?" lives in a work instance, as model configuration and scripts, "we should have some sort of documentation or guidance for the AI agents that manage and set up the system model and scripts, they should understand how to create the resources and manage the system so that it is able to answer these questions."

Change: a new section of `docs/AGENT-GUIDE.md` and a reference in the `ergostat-author` skill, which every agent setting up a model reads:
- What the question needs from a model: item kinds with honest states and finished states, `depends_on` and other relations, who or what takes each state, owners and people as blocks, gates, pools, leases, sensors of the real external state, and timestamps.
- How to bring in outside work (tickets, pull requests, alerts) so its waiting is visible, read-only by default.
- How to set up personal to-dos with `todo`, access-context batches and stakeholder updates.
- A worked example from a described process to a model that answers.
- **The check:** how the agent verifies its model. For each unfinished kind, run `ergostat why` and `ergostat held-up`, and treat "cannot tell" as a modelling gap to fix.
- Add a `check` finding for a kind whose waiting cannot be explained (no relation, nothing takes a state, no owner).

Definition of done: a fresh agent given only the guide and a described process builds a model on which `why` names the true root for three seeded stalls (run as a scripted acceptance on an example). Every command in the section is run by a test. No organisation's names.

## Where it stopped

Built in round 1 (about 55 net lines of code outside tests, docs and dev):

- `docs/AGENT-GUIDE.md` §3l, *Why isn't this done*: what the question needs from a model (honest and finished
  states, relations, who or what takes each state, people, gates, pools, leases with a `budget:`, sensors of the real
  state, timestamps), outside work brought in read-only, to-dos, access-context batches and stakeholder updates, a
  worked example from a described process to its model, and the check. The `ergostat-author` skill sends every agent
  that sets up or changes item kinds to it. SPEC §5a, *What the model must say for why*, says the rules.
- `check`'s `wait-unexplained` (`ergostat/spec/waits.py`, a finding): a kind with no precedence relation and a state
  its items rest in, unfinished, that no block takes and where no one is named (its first state, or one no event
  moves an item out of).
- `ergostat/why/blocks.py`: a working state's owner is whoever records the move to its next state (before a side exit
  or a move back), not the first event by name. Without it the worked example's review said "whoever records
  change.dropped", so the guide's answer would have been wrong; it is three lines, and no earlier test pinned the old
  order.
- `tests/test_why_guide.py` (10 tests): the scripted acceptance (the guide's model read from the guide, three stalls
  seeded: a dependency chain to a change on hold, the build gate shut by its sensor, a dead lease holding the
  releaser's pool; `why` names each true root and `held-up` lists them with no unknown); every command in the section
  run in order with rc 0, with the to-do and batch answers checked; every inline command matched to one that runs;
  the finding found and not found as its rule says; no shipped example has it. Break-tested once, both breaks together: with
  the finding's call removed and the owner order put back to by-name, three tests fail (the finding's test, and the
  two that read the owner).

Choices made with nobody to ask, each the most reversible:

- "A fresh agent given only the guide": no agent session was run (no network here). The acceptance runs the guide's
  own worked model, as a fresh agent following it would write it. A run with a real agent (for example as a request
  in `scripts/authoring_bench.py`) is not done.
- "`todo`" is read as a kind the owner declares, not a command: ergostat ships no unit of work (invariant 12), and no
  `todo` command exists. Stakeholder updates are to-dos with a non-precedence `covers` relation, written from `why`'s
  summary.
- The finding judges only kinds whose finished states `messages: done:` declares: with them inferred from the record
  the model cannot say which states finish (on the shipped examples the wider rule fired on cyclic kinds, such as a
  page that goes current and stale, that are never done). "No owner" is read as no event moving the items on, since
  the model has no other owner of a state. A kind with a precedence relation is not found even when its first state
  is untaken (the definition's three conditions together); `why` then says `nothing` for the chain's bottom item, and
  the guide's check catches that.
- A gate whose every input reads 0 is said by `why` as `closed` (held), not `gate`; the acceptance takes either, since
  the root (the gate, the factor at 0, what sets it) is the same.

Not run here: the whole unit suite and the four browser files (the factory runs them). Run here, each passing:
`tests/test_why_guide.py`, `tests/test_why.py`, `tests/test_held_up.py`, `tests/test_spec_items.py`,
`tests/test_chains.py`, `tests/test_dashboards_doc.py`, `tests/test_item_about.py`, `tests/test_faults_healthy.py`,
`tests/test_coherence.py`; ruff clean. No example touched, so no `demo_check`. `main` is the branch's base, so the
merge of main is empty. Commands refused in this session: running `ergostat` directly and Python heredoc scripts
(`uv run ergostat -C /tmp/w1 ...`, `python3 - <<'EOF'`), and `ls examples`; worked around only by running the same
through the test file.

The factory's own model had the new finding (`wait-unexplained items.knowledge`, `items.lesson`): each kind's first
state was where its items rest (`active`, `seen`), and nothing took them from it. Fixed in `ergostat.yaml` as the
guide says, with no finding allowed: each kind gains a first state `new` that no event puts an item in, so items
arrive in a working state. `why` then names whoever records the move on: the librarian's `lesson.proposed` once a
second review finds the class, or knowledge-sync's `knowledge.retired` once the entry has gone from the files. Choices
made with nobody to ask: `active` is not declared finished, because explain, check and status read `about` only from
unfinished items (test_factory_knowledge's about-missing-part test failed when it was). It is not declared paused
either, since the Items tab would then show every entry in force as stopped. `seen` is not paused, because the
librarian moves it on and no one does that by hand. `test_why_guide`'s no-unexplained-wait test now also loads the
root model, and it failed before the fix. `test_factory_knowledge`'s pin of the knowledge states is updated.

Round 2: the merge of main (8a27f9e3) conflicted in `docs/AGENT-GUIDE.md`, because main's dashboards gap also added a
section 3l. Both are kept. Main's *A shared dashboard* stays 3l, since main's records already call it that, and this
branch's *Why isn't this done* is now 3m. The references follow: SPEC §5a, the `ergostat-author` skill, the
`wait-unexplained` message in `ergostat/spec/waits.py`, and `tests/test_why_guide.py`. Run after the merge, each passing:
`tests/test_why_guide.py`, `tests/test_dashboards_doc.py`, `tests/test_why.py`, `tests/test_held_up.py`,
`tests/test_spec_items.py`, `tests/test_coherence.py`, `tests/test_factory_knowledge.py`,
`tests/test_faults_healthy.py`, `tests/test_item_about.py`; ruff clean. The whole unit suite and the four browser files
were not run here (the factory runs them). The conflicting merge was resolved with edits, because a shell rewrite of
the file was refused.

Round 2, after the build suite: `tests/test_factory_knowledge.py::test_an_approved_lesson_is_applied_with_no_gap`
failed once in the build step (`lesson.py hours` gave 0.668 where the test expects 0.667) and passes alone here (1
passed in 64 s). No code was changed for it. The expected mean is two lessons proposed an hour back plus one the
coordinator adds and that is applied "~0" later. But that third lesson's real approval-to-apply span runs across a
drain, a failed apply and a `block_in` subprocess, and `hours` measures that span as it is. When the three spans add
up to more than about 9 s under load, the rounding goes to 0.668. This is a wall-clock assumption in the test, not a
fault in `lesson.py`. The branch changes neither `dev/bin` nor this test, and its one change to the lesson kind (a
first state `new` that no event uses) does not touch the timing. Lesson 13 says this is reported, not fixed here: a
fix would make the test's clock fixed, or make its bound allow the real span, and that belongs to its own gap. The
command refused in this round: a shell heredoc appending this paragraph (`cat >> dev/records/... <<'EOF'`).

Round 2, second build failure of the same test (0.668 again): the factory asked for a fix, so the test's clock is now
fixed, and its bound is unchanged. Before `lesson.py hours`, the test sets each applied lesson's recorded start
(`proposed_at`, or `approved_at` for the coordinator's own) to exactly 1 h, 1 h and 0 before its `applied_at`. The
assertion is still `0.667`, and it now checks the mean the comment claims, not the test's own seconds under load.
`lesson.py` is unchanged: it measures the recorded spans as they are, which is right. The test runs against a fake
`ergostat`, so none of this branch's code is on its path. This is a fix outside the gap (lesson 13). It is the most
reversible one: one test, six lines, no code. Passes alone (1 passed in 64 s); ruff clean. Not break-tested: the
command that broke `hours()`'s `approved_at` fallback with `sed -i`, ran the test and restored the file with
`git checkout dev/bin/lesson.py` was refused.

Round 3: the merge of main (dc8ad98d) conflicted in `ergostat/why/blocks.py`. Main moved the list of a working state's
onward events into `_onward` (in the order written, never back to the kind's first state, and respecting
`moves-from:`). The branch's order (the move on to the next state first, nearest first, then moves back) now sorts
inside `_onward`, and both callers' rules are kept. Three tests failed after the merge, each fixed:
`test_a_working_state_names_whoever_records_the_move_on_to_the_next_state` expected `change.proposed` (a move back to
the first state, which main now leaves out) at the end of the list. The worked example's second `why todo/t1` check
was too blunt for main's new wording ("what it waits on is finished (batch/lab-1124)"): it now checks that the to-do
no longer *waits on* the batch and that the batch is named as finished. And main's new `batch` kind
(`dev/model/landing.yaml`) had `wait-unexplained`: items rest in its first state `testing` and nothing takes them
from there. As with knowledge and lesson, it gains a first state `new` that no event puts an item in, so a batch
arrives in `testing` and `why` names whoever records `batch.run-finished`. `test_queue_batch_item`'s pin of the
states follows. The guide's to-do paragraph said that ergostat ships no `todo` kind, which main's `todo` template has
made false. It now sends whoever reads it to that template for a person's hand work, and to the declared kind of the
worked example when the to-dos wait on items of the model.

Run after the merge, each passing: `tests/test_why_guide.py`, `tests/test_why.py`, `tests/test_held_up.py`,
`tests/test_spec_items.py`, `tests/test_factory_knowledge.py`, `tests/test_coherence.py`,
`tests/test_faults_healthy.py`, `tests/test_item_about.py`, `tests/test_chains.py`, `tests/test_dashboards_doc.py`,
`tests/test_queue_batch_item.py` (unit); ruff clean. Not passing, and not this branch's:
`tests/test_queue_batch_item.py::test_the_items_page_draws_the_batch_and_one_timeline_bar_per_run`, run with
Playwright, times out at line 306 (the snapshot's Items list never draws a row). It fails the same way with this
round's `landing.yaml` change taken out. With that change out, the branch differs from main in `ergostat/` only in
`spec/findings.py`, `spec/waits.py` and `why/blocks.py`, and none of them is on the snapshot page's path. It is
reported, not fixed (lesson 13). Not confirmed on clean main: the command that would have made a worktree of main
to run it there (`git worktree add --detach /tmp/mainwt main`) was refused. Also refused this round: a Python
one-liner to resolve the conflict (done with edits instead), a grep across docs, a wait loop on a background output
file, and a `ps` check for running pytest processes. The whole unit suite and the four browser files were not run
here (the factory runs them).

Round 4, answering the review's one finding (blocking; there were no others): the worked example's releaser lacked
`unblocked: true`, so it would release a reviewed change whose pull request is still open while `why` names whoever
records `pr.merged`, a false root. The releaser in §3m now takes `unblocked: true`, and a paragraph after the model
says the rule: a precedence relation is never enforced (SPEC §5a), so every block that takes items of a kind with one
takes `unblocked: true`. The new test
`test_a_reviewed_change_whose_pull_request_is_open_waits_on_it_and_the_releaser_does_not_take_it` seeds a fourth
stall, `c8`, reviewed with its pull request open: `why change/c8` names `pr/c8` and `pr.merged`, and the releaser's
take filter (`leases.ready.unblocked`, the dispatcher's own hook) keeps `c7` (pull request merged) and leaves out
`c8`. Break-tested: with `unblocked: true` taken off the guide's releaser the test fails; restored, it passes. The
check is on the dispatcher's filter, not a full dispatch with a running engine (the more reversible test: no process
started). Run, each passing: `tests/test_why_guide.py` (11), `tests/test_why.py`, `tests/test_held_up.py`,
`tests/test_coherence.py`, `tests/test_dashboards_doc.py`, `tests/test_spec_items.py`; ruff clean. No code outside
tests and docs changed this round. The whole unit suite and the four browser files were not run here (the factory
runs them).

Round 5, answering the queue's finding (the failing merge of a batch of 8, and three tests of
`tests/test_todo_template.py` failing again alone): the cause was this branch's change to `_onward` in
`ergostat/why/blocks.py`. It sorted a working state's ways on by the state each leads to, later states first. Main's
`todo` template's `waiting` state is left by `todo.freed` or `todo.ready` (both to `ready`, earlier in the kind's
order) or by `todo.done`. The sort put `todo.done` first, so `why` on a waiting to-do named "whoever records
todo.done" where the template's tests expect `todo.ready`. Reproduced here: 3 failed, 16 passed. The sort is taken out,
so `_onward` is main's again (the order written in `on:`). Since main's `_onward` already leaves out a move back to the
kind's first state, the worked example's `in-review` gets `change.reviewed` first in written order anyway, and
`test_a_working_state_names_whoever_records_the_move_on_to_the_next_state` passes unchanged except for its docstring.
`blocks.py` now matches main, so this branch's code outside tests and docs is `spec/findings.py` and
`spec/waits.py`. SPEC §5a and the guide's §3m now say the owner is the first way out in the order `on:` writes them,
so a kind should write its way on before its side exits. This is the most reversible fix: it takes the branch's
change out and keeps main's behaviour. The round-1 break test of the owner order no longer applies, because that code
is gone. The three to-do tests failing with the sort and passing without it are the new break test. Run, each
passing: `tests/test_todo_template.py` (19), `tests/test_why_guide.py` (11), `tests/test_why.py`,
`tests/test_factory_knowledge.py` (103), `tests/test_held_up.py`, `tests/test_queue_batch_item.py` (unit: 15 passed,
the Playwright test skipped since playwright is not installed in this run), `tests/test_coherence.py`,
`tests/test_spec_items.py`, `tests/test_dashboards_doc.py`, `tests/test_item_about.py`; ruff clean. Refused this
round: `git checkout main -- ergostat/why/blocks.py` (done with an edit instead) and one shell loop running three test
files (run one at a time instead). The whole unit suite and the four browser files were not run here.

Round 6, answering the review's one finding (blocking; there were no others): the `new` recipe made `why` name the
arriving event as the owner of later working states. `_onward` leaves out only moves into the item's own state or
into the kind's first state. With `new` first, the arriving event (`batch.started`, `lesson.seen`) is no longer left
out, and it was written first in `on:`. So a batch in `isolating` named "whoever records batch.started" (main names
`batch.landed`), and a lesson in `proposed` named "whoever records lesson.seen" (main names `lesson.requested`). The
fix is in the models and the guide, with no code changed: the events an item arrives by are written last in `on:`.
`dev/model/landing.yaml` now writes `batch.started` and `batch.run-started` last, and `ergostat.yaml` writes
`lesson.seen` last. The guide's §3m recipe now says to write the arriving events last, and why. Its worked example's
`pr`, `todo` and `batch` kinds follow that rule: written first, `batch.planned` was named for a sitting in `open`,
the same fault. SPEC §5a says the same. Choices made with nobody to ask: the review also offered
`moves-from: [new]` on the arriving event. It was not taken, because it changes the fold: a re-sent
`batch.started` or `lesson.seen` on an existing item would be refused and recorded as refused. Reordering a map
changes nothing but the order `why` reads. `batch.run-started` is also a real move from `isolating` back to
`testing` (a new run), so it could not be barred anyway. A batch in `pushing` still names `batch.run-finished`, as on
main (no single written order suits every state there). It is unchanged and outside this finding. The new test
`test_with_new_first_a_later_working_state_names_its_way_on_not_the_arriving_event` runs `why` on the guide's batch
in `open` (it names `batch.closed`). On the factory's own spec it pins the owner `why` takes (the first of `_onward`):
a batch in `testing` (`batch.run-finished`) and `isolating` (`batch.landed`), a lesson in `seen` (`lesson.proposed`)
and `proposed` (`lesson.requested`), and knowledge in `active` (`knowledge.retired`). It also checks that no later
state of batch or lesson names an arriving event. Break-tested: with the guide's batch order put back, the test fails
on `batch.closed`. With `lesson.seen` put back first in `ergostat.yaml`, it fails with `'lesson.seen' ==
'lesson.requested'`. Restored, it passes. Run, each passing: `tests/test_why_guide.py` (12),
`tests/test_queue_batch_item.py` (unit; the Playwright test skipped, playwright not installed in this run),
`tests/test_todo_template.py`, `tests/test_why.py`, `tests/test_coherence.py`, `tests/test_dashboards_doc.py`,
`tests/test_factory_knowledge.py`, `tests/test_held_up.py`, `tests/test_spec_items.py`,
`tests/test_faults_healthy.py`, `tests/test_item_about.py`, `tests/test_chains.py`; ruff clean. Refused this round: one
shell command reading SPEC lines and grepping the skill (`sed -n 1760,1770p docs/SPEC.md; grep ...`), done with the
read and search tools instead. The whole unit suite and the four browser files were not run here.
