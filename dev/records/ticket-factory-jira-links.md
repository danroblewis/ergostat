# ticket-factory-jira-links: the ticket factory's watcher reads Jira's issue links and parent and records them as the ticket's relations
depends-on: []

## Definition of done

The gap is the clause of "Relations, what is left" in `docs/GAPS.md` that says `ticket-factory` does not record Jira's links. Today `bin/jira.py` asks Jira only for summary, status, labels and description, and the `ticket` kind declares no relations. When this branch is done, every point below holds.

1. **The ticket kind declares relations** (`examples/ticket-factory/ticket.yaml`):
   ```yaml
   relations:
     blocked_by: ticket
     duplicates: {kind: ticket, inverse: duplicated_by}
     relates_to: {kind: ticket, precedence: false}
     parent: ticket
   ```
   Every target id is `ticket/KEY`. A Jira parent (an epic, or a sub-task's parent) that the factory never found stays an id that was never recorded. SPEC §5a already says such a link is "kept, and said". No epic kind is added, and no transition or block changes. `takes:` stays as it is, without `unblocked`, so nothing is enforced.

2. **`bin/jira.py` reads links in one place.**
   - **`links(fields) -> dict[str, list[str]] | None`** is a pure function from one issue's raw Jira `fields` to `{"blocked_by", "duplicates", "relates_to", "parent"}`, each a sorted list of `ticket/KEY` ids.
   - **The mapping, by link type name:**
     - `Blocks` with an `inwardIssue`: blocked_by. With an `outwardIssue`: nothing, because that direction is the inverse `blocks`, which ergostat derives.
     - `Duplicate` with an `outwardIssue`: duplicates. With an `inwardIssue`: nothing (the inverse).
     - Any other type name, in either direction: relates_to.
     - `fields.parent.key`: parent. A missing or null `parent` means no parent.
   - **Fails closed (lesson-3).** `links()` returns `None` for the whole issue when any part can't be read:
     - `issuelinks` is missing or is not a list;
     - an entry is not a dict;
     - an entry has no string `type.name`;
     - an entry has neither `inwardIssue` nor `outwardIssue`;
     - a linked issue has no `key`, or a key that is not a string;
     - `parent` is present and not null, but is not a dict with a string `key`;
     - any key fails the allowlist `^[A-Z][A-Z0-9_]*-[0-9]+$`.

     An issue whose links come back `None` gets no write at this reading.
   - **`linked() -> dict[str, dict | None]`**: one search over `_scope()` (all labelled issues) with fields `["issuelinks", "parent"]`. It returns `links()` of each issue, keyed by Jira key.
     - The search asks for at most `LINKS_MOST = 500` issues, a constant like `counts()`'s. Issues past 500 are not looked at, so they keep what they have.
     - It works for both Cloud and DC through `_search`.
     - Offline, it reads raw Jira-shaped `issuelinks`/`parent` from `fakes.jira_linked()` and runs the same `links()` parser.
   - The module docstring lists `linked()` and `links()`.

3. **The fake board has links** (`bin/fakes.py`). Each fake issue carries `issuelinks` (default `[]`) and may carry `parent`. SCRUM-2 is made with a `Blocks` `inwardIssue` SCRUM-1, so the offline demo shows a blocked ticket. `jira_linked()` returns `{key: {"issuelinks": ..., "parent": ...}}` for the labelled issues on the board, moved on to now the way `_issues` does it.

4. **The watcher records the links** (`bin/watch.py`, `look`). At each reading, after the found pass and after `watch.json` is written:
   - It reads `jira.linked()`. For each key whose ticket is in the record (`known`, as read at this reading's start) or was found at this reading (counted as having no links), and whose links are not `None`, it compares each relation's set with the ticket's folded field.
   - When a relation differs, it gives `found()` one event: `{"event": "ticket.linked", "item": tid, "data": {rel: {"set": ids}}}` for the relations that differ only.
   - When none differ, nothing is written.
   - A labelled issue that is not a ticket in the record and was not just found is never written. `ticket.linked` must not create items.
   - If `jira.linked()` raises `JiraError`, nothing is written, the error goes to `tf.log`, and the arrivals reading is still answered.
   - Daemon mode records through the socket as the sensor's own, as `ticket.found` does now. Manual mode prints.

5. **The claim is narrowed (lesson-1, lesson-8).** No lock is taken and none is claimed. Each reading compares Jira's answer with the fold as read at that reading, and the write is a full `{"set"}`. If two readings overlap (the daemon and a manual run whose output is recorded), the older answer may land last. The record then matches Jira's latest answer again **after the next reading**, not at once. `watch.py`'s docstring and the ticket-factory README say exactly this and nothing wider.

6. **Docs.**
   - `examples/ticket-factory/README.md`: the watcher row, and a line under the watcher's daemon, say that it records Jira's links as `blocked_by`/`duplicates`/`relates_to`/`parent` with the mapping above. They also give the catch-up claim, the 500-issue cap, and that an issue with an unreadable link keeps the links it has.
   - `docs/GAPS.md`: the ticket-factory clause of "Relations, what is left" is removed. It may be noted as done, with this branch named.
   - SPEC is not changed. Nothing in ergostat changes.

7. **House done.** The acceptance tests exist and pass. The unit suite and the four browser files pass with rc 0. Ruff is clean. `scripts/demo_check.py ticket-factory` passes. origin/main is merged in and the suites are run again (lesson-7). For each new test, the report says which line was broken to watch it fail (lesson-9).

## Files to touch

- `examples/ticket-factory/ticket.yaml`
- `examples/ticket-factory/bin/jira.py`
- `examples/ticket-factory/bin/fakes.py`
- `examples/ticket-factory/bin/watch.py`
- `examples/ticket-factory/README.md`
- `docs/GAPS.md`
- `tests/test_ticket_factory_links.py` (new)
- `tests/test_ticket_factory_daemons.py`, only if an existing count of a ticket's events changes because of `ticket.linked`. Any such change must be said in the report.

## Risks

- **lesson-1** (check, then write, without the lock): the fold is read at the start of `look()` and written after a Jira call, with nothing held in between. Two readings that overlap can land the older answer last. Answer: no lock is claimed. A full `{"set"}` is compared against the fold at every reading, never against a local cache of what was last written, so the next reading puts it right. A test puts the newer reading's write inside the gap.
- **lesson-3** (failing open): the risks are a malformed link entry, a linked issue or parent with no key (hidden by permissions), `issuelinks` missing, and Jira failing on the search. If these were dropped or counted as empty, the full-set write would clear a real `blocked_by`. Answer: `links()` returns `None` for the issue and nothing is written for it. A failed search writes nothing.
- **lesson-5** (stale state under a reused id): if links were added rather than set, a link removed in Jira would stay on the ticket for ever. Answer: `{"set": ...}`. A test removes a link.
- **lesson-4** (a limit with no ceiling): the links search is capped at a constant 500, not read from config. A test asserts the `maxResults` sent.
- **lesson-8** (a claim wider than the code): "the record mirrors Jira" would be too wide. The docs say "after the next reading", "an issue past 500 or with an unreadable link keeps what it has", and "tickets only". Each of these is tested below.
- **lesson-9** (a test that can't fail): each test below names the break it catches. The implementor breaks each guarded line and reports the failure.
- **lesson-7** (merges): `ticket.yaml`, `bin/jira.py` and the watcher are also touched by the related relations gaps. Merge origin/main and run again.
- **lesson-13** (stay inside the gap): no change in `ergostat/`. A failure elsewhere is reported, not fixed here.

## Acceptance tests

All tests are in `tests/test_ticket_factory_links.py`. A fixture copies the example offline (as `test_ticket_factory_daemons.factory` does), sets `TF_OFFLINE=1`, `ERGOSTAT_HOME` and `ERGOSTAT_CMD=<python> -m ergostat -C <copy>`, and leaves `ERGOSTAT_SOCKET` unset so records and folds go through the real `ergostat` CLI. It imports `tf`, `fakes`, `jira` and `watch` from the copy's `bin/` with `sys.path` set and those modules popped from `sys.modules` before and after each test. Fake board edits go through `fakes._state("jira")`.

- `test_jira_links_are_read_as_relations`: `links()` maps each case to the expected sorted ids: Blocks inward to blocked_by, Blocks outward to nothing, Duplicate outward to duplicates, Duplicate inward to nothing, Relates and a custom type to relates_to, `parent` to parent, and a missing or null parent to `[]`. *Fails if* the inward/outward sense is swapped, or the inverse directions are recorded.
- `test_an_unreadable_link_makes_links_none` (parametrized): each case returns `None`. The cases are: an entry with neither inwardIssue nor outwardIssue; a linked issue without `key`; a parent without `key`; an entry without `type.name`; a non-dict entry; `issuelinks` missing; `issuelinks` not a list; and a key `"../x"` failing the allowlist. *Fails if* any one is skipped instead of returning `None` (lesson-3).
- `test_a_malformed_entry_beside_a_blocks_link_leaves_blocked_by_unchanged`: one reading records `ticket/SCRUM-2` `blocked_by == ["ticket/SCRUM-1"]`. The fake board then gains, on SCRUM-2, an entry with neither side next to the Blocks link. After another reading, `blocked_by` is still `["ticket/SCRUM-1"]` and no new `ticket.linked` event exists for SCRUM-2. *Fails if* the malformed entry is dropped and the set is written (the lesson-3 review point).
- `test_a_link_removed_in_jira_is_removed_from_the_ticket`: the Blocks link is removed from the board. After the next reading, `blocked_by == []`. *Fails if* links are added rather than set (lesson-5).
- `test_an_unchanged_answer_records_nothing`: two readings with the same board give exactly one `ticket.linked` for SCRUM-2. *Fails if* it writes every reading.
- `test_a_newer_reading_in_the_check_to_write_gap_is_caught_up_next_reading`:
  1. Reading 1 sees answer A (SCRUM-2 blocked by SCRUM-1).
  2. The test monkeypatches the write of reading 1's `ticket.linked`. Before letting it land, the patch edits the board to answer B (blocked by SCRUM-3) and runs a whole second reading, which records B. Then A lands last.
  3. The test asserts that the fold is A, so the gap really was hit.
  4. One more reading with answer B runs, and the test asserts the fold is `["ticket/SCRUM-3"]`.

  *Fails if* the watcher compares against a local "last written" cache instead of the fold, or if the claim "after the next reading" is false (the lesson-1/lesson-8 review point).
- `test_links_are_written_only_for_tickets_in_the_record`: a labelled fake issue in "In Progress" that was never found, with a Blocks link, gets no item and no event after a reading. *Fails if* `ticket.linked` is written for unknown keys.
- `test_a_ticket_found_at_this_reading_gets_its_links_at_once`: on a fresh board, the first reading records `ticket.found` and then `ticket.linked` for SCRUM-2, and its fold has `blocked_by`. *Fails if* just-found tickets are skipped.
- `test_jira_failing_on_links_writes_nothing_and_the_reading_is_still_answered`: `jira.linked` is monkeypatched to raise `JiraError`. `watch.read(["arrivals.main"])` returns its number, and the recorded links are unchanged. *Fails if* the error escapes, or is counted as "no links" and clears them.
- `test_the_links_search_asks_for_links_and_parent_capped` (parametrized over `JIRA_API` 2 and 3): with `OFFLINE` forced off and `_call` monkeypatched to capture the request, `linked()` asks for the fields `issuelinks` and `parent`, the `_scope()` JQL, and a cap of 500. *Fails if* the cap or the fields change (lesson-4).
- `test_the_offline_daemon_records_a_blocked_ticket`: `bin/watch.py serve`, with one read line piped in (as in `test_each_daemon_answers_lines_piped_by_hand`), still answers 18.0, and the record holds `ticket/SCRUM-2` `blocked_by == ["ticket/SCRUM-1"]` with source `arrivals.main`. The model loads (`check` clean) with the new `relations:`. *Fails if* the daemon path does not write, or the kind's relations do not compile.
- The existing `tests/test_ticket_factory_daemons.py` passes unchanged. If it doesn't, the report gives the change and why. `scripts/demo_check.py ticket-factory` passes.

## Size budget

160 net lines of code outside `tests/` and `docs/`: about 60 in `jira.py`, 25 in `fakes.py`, 35 in `watch.py`, 8 in `ticket.yaml`, and the rest in docstrings. The README is documentation and is not counted.

## Notes from the plan review (answer each)

- lesson-8, the 500 cap: the only test checks the `maxResults` sent. Jira Cloud's search returns at most about 100 per page when fields are asked for. If `_search` does not page, the real cap is 100 and the README's 'past 500 keep what they have' is wrong. The implementor must check how `_search` pages. Then either page up to 500 or state the real cap, and add a test where an issue past the cap keeps its relations.
- lesson-8, parent on DC: on Data Center, an epic is a custom field (Epic Link), not `fields.parent`. So 'a Jira parent (an epic, or a sub-task's parent)' is too wide for API 2. The README should say epics are recorded as parent only where Jira returns them in `parent`, or the code should read Epic Link. Either way, add a test.
- lesson-3, the limit on failing closed: Jira usually leaves out a link to an issue the user can't see. It does not send it without a key. So a link hidden by permissions looks like a removal and the full set clears it. Nothing can detect this. The README must say the record only holds links the Jira account can see, and the claim must not suggest otherwise.
- Matching on the type name (`Blocks`, `Duplicate`) breaks silently if an admin renames a type: Blocks would then go to relates_to. Either match on the type's inward/outward strings or its id as well, or say in the README that it matches by name.
- If one bad link entry fails an issue closed, that ticket's relations stay frozen for as long as the entry exists. The watcher should write a line to `tf.log` naming the key each time, so this is visible. Test that one None issue in a batch does not stop writes for the others.
- The check-to-write gap test patches the write and then runs a second reading inside the patch. The patch must only hold back the first call, or it will recurse and catch the second reading's own write. Show in the report that the inner write was really recorded before A landed.
- relates_to is recorded from both ends, since Jira shows the link on both issues. Say whether ergostat treats the relation as symmetric, or whether each side holds its own copy. Either way, test that removing it in Jira clears both sides.
- Each reading now makes an extra search across up to 500 issues with issuelinks. State how often the daemon polls and confirm this stays within Jira's rate limits, or read links less often than arrivals.
- Confirm that a sensor source may write relation fields through the socket. If not, the daemon test catches it, but the report should name the rule that allows it.
