# notify: everything waiting on a person, answerable and delivered

Branch `notify`, from main (07a07c1). Asked by the owner (2026-11-19): human approval should be rare (the early
stages of a system, while its feedback loops are worked out; then it graduates up the ladder: an AI approver, narrow
AI, a program, a rule), but while it is used it must reach the person and be quick to answer, from the CLI and the
UI. Today nothing pushes: held approvals and person requests wait until someone opens the page or runs `ergostat`.
The `repair` branch's `apply-fix` is a gated action with `gate: approve`, and `impact` gives each fix a report; this
branch is how such approvals reach a person and are answered. It keeps to the generic gated-action interface.

## Definition of done

**One inbox.** Everything waiting on a person, in one list: held gated actions (SPEC §12k), person-block requests
(`person.asked` not yet reported), advise-mode commands (`block.advised` not yet approved or denied), step tests
offered (recorded `steptest.offered` when a loop's analysis offers one, still current and undecided) and model
changes awaiting the owner (the review queue; with a judge, those it passed). Each entry has an id (`KIND/KEY`; any
unique start of the key will do), a one-line summary, its age, a link to its item or block page, its answer verbs
(`approve`/`deny`, or `done`), why it waits (for an action about an item: the item's `impact` sentence and `tests`
result, when the item has them), and its class's record. **CLI:** `ergostat inbox` lists them; `ergostat inbox ID
--approve|--deny [--note]` or `--done N` answers any kind through the existing paths (`gate.approve`/`deny`,
`block.approved` (and a new `block.denied`), a person's report, `control.proposals.accept`/`dismiss`, the review
queue's `accept`/`dismiss`); `--json`; `--stats`. **MCP:** `inbox` and `answer`. **Page:** the existing "Needs
attention" side panel lists the entries first, each with Approve / Deny (or a number and Done) inline, posting
`POST /api/inbox/ID/VERB`; the item pages keep their own buttons. No new page or panel. Answers are events from the
owner, as today.

**`notify:`** (top level, main file): `channels:` of type `macos` (terminal-notifier if present, else osascript),
`email` (`to:`, `command:`, default `sendmail -t`), `slack` / `discord` (a webhook URL from `url-env:` or
`url-file:`, never written in the YAML), and `command` (`run:`, the message on standard input: the fake channel tests
and demos use). **Each delivery is a gated action** `notify.CHANNEL` (the channel's `gate:`, default `auto`), so a
channel the owner sets to `deny` sends nothing and is recorded as denied. The message: the summary, why it waits, and
a link to the entry's page from `base-url:` (default: the running page). New entries within `group:` (default 2m)
become one message; at most `per-hour:` (default 6) messages an hour per channel; `quiet:` hours (`22:00-07:00`)
optional. Recorded as `ergostat.notify.sent` events (channel, entries, the action); never about a `notify.*` action
of its own (the cause-chain guard). Swept by the engine's clock.

**Escalation and the approval budget.** `wait-at-most: X`: an entry waiting longer is a finding
(`waiting-on-owner`) and is notified once more, to `escalate-to:` channels when given, else to every channel. The
measures `ergostat.inbox.waiting`, `ergostat.inbox.oldest` (hours) and `ergostat.inbox.asked` (entries asked over the
last day) may be read by a `builtin:` sensor, so a goal can hold them; `asks-per-day: N` makes more than N asked over
the last day a finding (`approvals-over-budget`) naming the class asking most and its rung up.

**Graduation.** Per class (an action's class, `advise:BLOCK`, `change:KIND`, `steptest`, `person:BLOCK`) over the
last week: asked, approved, denied, median time to answer; shown on each inbox entry and by `ergostat inbox --stats`,
with one line when a class is always approved (at least 5, none denied): `gate: auto` or an AI approver for an
action, `mode: auto` for an advised block, the judge's `accept: auto` for a kind of change. Nothing is changed
automatically.

**Docs:** SPEC (a section on the inbox, notify, escalation and the budget; §12k and §15 point to it) and the agent
guide (human approval is for the early stages; setting notify up; graduating).

## Acceptance tests (`tests/test_inbox.py`, `tests/test_inbox_page.py`)

- `test_the_inbox_aggregates_every_kind`
- `test_each_kind_is_answered_from_the_cli`
- `test_each_kind_is_answered_from_the_api`
- `test_the_mcp_lists_and_answers`
- `test_new_entries_within_the_window_are_one_message`
- `test_at_most_per_hour_per_channel_and_quiet_hours`
- `test_a_delivery_passes_through_its_gate_and_a_denied_channel_sends_nothing`
- `test_a_notify_action_held_is_never_notified_about`
- `test_channel_commands_are_built_without_the_url_in_the_yaml` (slack, discord, email, macos: commands checked, the
  delivery's subprocess patched: no network)
- `test_an_entry_past_wait_at_most_is_a_finding_and_escalated_once`
- `test_the_budget_and_an_always_approved_class_are_suggested_up_the_ladder`
- `test_notify_is_checked`
- `tests/test_inbox_page.py::test_approve_in_the_side_panel` (Playwright: Approve on a held action in Needs
  attention; the action is approved and the entry leaves the panel)

No test or demo sends a real notification, email or webhook: the `command` channel writes to a file.

## Size budget

**700 net lines** of code outside `tests/` and `docs/` (asked by the owner for this branch).

## Suites

`uv run python -m pytest -q`; the Playwright files with no skips; `uv run ruff check ergostat tests scripts`;
`demo_check.py ticket-factory`. Hand-started servers on 8791-8797.
