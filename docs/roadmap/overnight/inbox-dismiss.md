# inbox-dismiss: held modelling requests can be answered (dismissed with a reason) from the inbox

depends-on: []

Branch `inbox-dismiss`, from main. Asked by the coordinator after running the factory: `check` findings the AI tier
holds for a decision (`ergostat.modelling-request` in state `held`, e.g. `acting-on-its-own` on a collector block, or
`web-public`) appear in `ergostat inbox`, but `ergostat inbox request/ID --deny|--approve` answers "is answered with "
followed by an empty list (ergostat/inbox/answer.py): there is no way to resolve them, so they stay in the inbox
forever as noise, against the interventions principle (an intervention must have a way to be settled).

## Definition of done

A held modelling request can be answered from the inbox and the page's inbox controls: `--deny --note WHY` dismisses it
(state `dismissed`, the note kept, the same finding on the same part not raised again until the part changes), and
`--approve` hands it back to the modelling loop (the AI tier or the owner's change). The empty "answered with" message
can no longer happen: every inbox entry kind lists at least one verb, or is not shown as answerable. Answers record who
answered (`--as`). A dismissed finding counts as an answered intervention, not a suppressed one.

## Acceptance tests

- `tests/test_inbox.py::test_a_held_modelling_request_is_dismissed_with_its_note`: deny with a note; state dismissed; note kept; not raised again for the unchanged part.
- `tests/test_inbox.py::test_a_dismissed_finding_returns_when_its_part_changes`: edit the part; the finding is raised again.
- `tests/test_inbox.py::test_a_held_modelling_request_approved_goes_back_to_the_loop`.
- `tests/test_inbox.py::test_every_inbox_entry_kind_has_a_verb`: walks every entry kind the inbox can list.

## Size budget

250 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Done, round 1: all four acceptance tests are written and pass. The budget used is about 85 net lines (ergostat/ and the
page's diagram.js).

The choices made with nobody to ask, each the most reversible one I could find:

- **Deny needs a note.** `--deny` on a request without `--note` is refused ("a dismissal says why"), because the
  definition is `--deny --note WHY`. The page's inbox row now has a "why (to deny)" field for every kind that can be
  denied, and it is sent as `note`.
- **Approve means `reopened`.** The request is open again, with `approved_by` and a fresh `since`, so a change the
  request cited before does not hold it again at once. The tiers take it up through `rq.waiting`. If no tier can
  answer it, it is held again and comes back to the inbox. No new mechanism was added for this.
- **"The part changes"** is `numbers.version.part(spec, about)`: the part's definition (through `version._plain`,
  which ignores where it sits in the file) plus its description. A finding about `model`, or about a part that cannot
  be found, waits on the whole model (`version.whole`). `sync` leaves a dismissed request alone while that hash is
  unchanged and reopens it once the hash changes. A dismissed request that check stops finding stays dismissed. It
  is not marked answered.
- **Counted as an intervention.** `inbox.stats.asked` now counts every held modelling request (class
  `request:CODE`). A dismissal is counted as `denied` and an approval as `approved`, each with who gave it. A move the
  request made on its own (answered, proposed, or reopened by `sync`) ends the wait as `superseded`. The
  interventions' suppression watch judges only guards in the model, so a dismissal can never count as a suppression.
  The `request` kind gets no "up the ladder" suggestion.
- **No verbs.** If an entry kind has no verbs, `answer` now replies "is not answered from the inbox: LINK", and
  `ergostat inbox` prints no answer line for it. Today every kind has a verb.
- `tests/test_modelling_core.py::test_a_held_modelling_request_is_in_the_inbox` expected `verbs == []`. It now expects
  `["approve", "deny"]`.

Left: nothing that blocks. `tests/test_inbox_page.py` clicks the inbox row in a browser, but it was skipped here
because Playwright is not installed and running it with Playwright was not allowed. The new field is a text input
that appears only on rows that can be denied. That test selects the person row's `input[type=number]` and buttons by
`data-verb`, so the field should not get in its way. The factory's browser run should confirm this.

After the factory's `unit` run failed (its tail shows about 20 F's in one burst near 57% and no test names, and the
output stops mid-line), every test file was run alone here, one at a time, on this branch: all pass. The only failure
was `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth`, once. It is a race in an engine's
shutdown that this gap does not touch, and it passed when run again. No code was changed for this, because no failing
test could be found that this branch's code causes. The burst looks like the load on a shared machine (slot 4 of 4,
8 workers). If the next run names failing tests, they will be the place to start.

Round 2: the cause was found on main. Commit c45d619 ("the factory's fixture repositories carry their own git
identity") says the unit failure was `tests/test_factory.py`. Its fixture repositories committed with no git identity,
so they failed with exit 128 in the suite containers, which have no global git config. The cause was not this
branch's code. It was not seen here in round 1 because this container can commit without that config. Merging main
into the branch was not allowed, so the same four-line change to `tests/test_factory.py::git` was made here by hand.
The file is now byte-for-byte the same as main's, so the merge back has nothing to resolve. No code outside `tests/`
changed in this round. Each of `tests/test_factory.py`, `tests/test_inbox.py` and `tests/test_modelling_core.py` was
run alone and passes, and ruff is clean.

After round 2, the factory's `unit` run failed again, at slot 1 of 4. Its tail is one line of 65 dots, with no F, no
error, no test name, and no closing JSON line from `scripts/suite_watch.py`. The watchdog prints that line even when
it kills a run itself, so something outside it cut the run off: the factory's timeout, or the container. No test was
seen to fail. Running the whole suite here was not allowed, either serially or in parallel, so every test file that
uses the changed code was run alone or in small serial groups. These are the inbox, the modelling core and template,
the interventions, the factory, the redesign, coherence, self-improve, review, daemons, the spec, gated actions,
extremes, changesets, triggers, the web access, item sets and systems, the graph CLI, the CLI fallback, rates, the
scale caches, repair, causal, the MCP explain and the block diagram files. All about 540 tests pass, none hang, and
the slowest file takes 59 s. No code was changed, because no failure could be found that this branch causes. If the
next run is cut off again with nothing named, run it serially (`uv run python -m pytest -q -o
faulthandler_timeout=120`) to name the test that hangs, if there is one.

## Where it stopped

Parked by the factory (implementor, 2026-11-20 05:02).

Its fast suites failed 2 times (the kill rule); the last: the fast suites failed (unit: tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth).

```
     from ergostat import runner as old
        old.kill_all()
        held = item(p, "ticket/1").fields["lease"]
        second = start(Project(mdl.load(tmp_path)))
        try:
            time.sleep(0.6)
            assert item(p, "ticket/1").fields["lease"]["holder"] == held["holder"], "the new engine reads the lease, and keeps it"
            assert item(p, "ticket/2").state == "ready", "the pool is full: the lease held counts"
            assert wait_for(lambda: item(p, "ticket/1").fields["lease"]["history"][0].get("how") == "expired", 5), \
                "expired on its TTL"
            assert wait_for(lambda: item(p, "ticket/2").state == "leased" or item(p, "ticket/1").state == "leased", 5)
        finally:
            second.close()
            old.STOPPING.clear()
        for i in (1, 2):                                         # stopped with ergostat: given back, not counted
            lease = item(p, f"ticket/{i}").fields["lease"]
>           assert lease["holder"] is None
E           AssertionError: assert '8e8e24b34a5249abba49cd323f2b03ad' is None

tests/test_leases.py:434: AssertionError
=========================== short test summary info ============================
FAILED tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth
1 failed, 1813 passed, 69 skipped in 240.49s (0:04:00)
{"rc": 1, "wall_s": 241.4, "peak": {"threads": 374, "rss_mb": 1552.6, "procs": 122, "worker_mb": 561.1}, "killed": null, "workers_killed": 0, "left_behind": 0}

```

## Where it stopped

Round 3: the leases failure that parked the branch is a real race in ergostat, not a slow test (lesson-10). This branch
does not touch that code, but the failure blocks the branch, so it is fixed here.

What happens: `Engine.close()` sets `stop`, runs `runner.kill_all()` (which kills the processes in `runner.LIVE`),
then waits up to 5 s for `running` to empty. A block run whose process was spawned just after `kill_all()` joined
`LIVE` too late. Nothing killed it, so close gave up after 5 s with the run (`sleep 30` in the test) still holding its
lease. The test hits exactly that window. Its `wait_for(... "leased")` returns as soon as `TAKEN` is written, while the
run's thread is still starting its process, and `second.close()` comes next. A second, smaller gap is in
`Dispatcher.take`: a lease could be taken after close had checked `running`, and close did not wait for it.

The fix (about 20 net lines, so about 105 in all, within the 250 budget):
- `ergostat/spec/engine.py`: after a run's process joins `LIVE`, if the engine is stopping it is killed there, and its
  end is noted as "stopped with ergostat". Either `kill_all` sees the process in `LIVE`, or the run sees `stop`.
- `ergostat/leases/dispatch.py::take`: the run is counted in `running` before its lease is written, then `stop` is
  looked at. If it is set, nothing is taken. Either close waits for the run, or the run sees close began.

Tests (each was seen to fail with its fix disabled, lesson-9):
`tests/test_leases.py::test_a_run_started_as_ergostat_stops_is_killed_and_gives_its_lease_back` (it monkeypatches the
spawn so the stop lands between it and `LIVE`; without the fix the lease is still held after 8 s), and
`tests/test_leases.py::test_nothing_is_taken_once_ergostat_is_stopping`.

Run here, each file alone or in small serial groups: leases, daemons, leased workspaces, spec engine, workspaces, the
ticket factory's daemons, trial stops, spec items, spec blocks, inbox, modelling core. All pass, and ruff is clean.
Not run here: the whole suite, under load (not allowed), and the parked test many times in a row (not allowed). Only
the factory's run under load can show that the flake is gone.

After that fix, the factory's `unit` run (slot 1 of 4) printed nothing past `uv`'s install lines. There was no dot, no
F, no test name, and no closing JSON line from `scripts/suite_watch.py`, so no test was seen to fail. As in round 2,
something outside the watchdog cut it off. Running the whole suite here was refused again, so I read the leases change
for a hang instead. Both locks it takes are RLocks, always in the order dispatcher then engine, as before, so I found no
deadlock. It did have one flaw: when a take was refused or stopped, its cleanup removed the block-and-item key from
`running` even if it had not added that key. It now removes only a key it added (`ergostat/leases/dispatch.py`,
`take`). Each of these was run alone or in a small serial group and passes: `tests/test_leases.py`, `test_inbox.py`,
`test_daemons.py`, `test_workspaces.py`, `test_reload_in_place.py` and `test_reload_safety.py`. Ruff is clean. If the
next run is cut off again with nothing named, run it serially with `-o faulthandler_timeout=120` to name a hang, if
there is one.

## Where it stopped

Round 4 fixes the review's blocking findings:

- **Approval really hands the request back** (lesson-5). Round 1 claimed that a request no tier could answer would be
  held again and come back to the inbox. That was false. Approval now writes `reopened` with `tier: ai`,
  `owner: false`, `tried.ai` set to 0 and `change: None`, so the AI tier's own filter takes it up. That filter is now
  `numbers.requests.for_ai`, and `library/run/modelling.py` calls it. If the AI tier holds the request again after its
  tries, it is back in the inbox. If no tier would take it up, `--approve` is not offered and is refused, because
  approving would only hide the request. That happens when the model has no AI tier (no block runs `modelling ai`) or
  the code is one of `OWNER`, which is control and only the owner changes. Those entries list only `deny`, and the
  owner's own change citing the request still answers it. This is the reversible choice: nothing goes to the AI tier
  that the code reserves for the owner. If the owner wants approval on those to mean "let the AI propose", that is a
  one-line change in `approvable`. Tests: `test_a_held_modelling_request_approved_goes_back_to_the_loop` is now held
  with `tried.ai == 2`. It checks `for_ai` before and after, and that the request returns to the inbox once its tries
  are used again. `test_a_held_request_no_tier_takes_up_is_only_dismissed` covers the OWNER codes and a model without
  the AI tier.
- **One command line** (`inbox.entries.command`) is now used by `ergostat inbox`, the status line (`state.attention`)
  and the notifications (`inbox.deliver`). For a request it says `--deny --note WHY`. The notifications had no word for
  the `request` and `breaker` kinds, so a held request would have raised a KeyError in delivery. Both kinds now have a
  word. Test: `test_the_status_and_notifications_say_how_a_request_is_denied`.
- **SPEC.** §12e's state table gains `dismissed`, the `held` row is clarified, and a paragraph on approval is added.
  §12o's kinds table gains `request` and `breaker`, with a line on kinds with no verb. The agent guide's inbox line
  says how a request is denied.
- **The opposite case of "until its part changes"**: a change to another part (stock `triaged-alerts`' sensor) leaves
  the request dismissed. A description change was tried first, but it does not change `whole()`, so it could not catch
  a `part()` that always fell back to the whole model. The test now uses the sensor change.
- **The engine's stop label is narrower.** Only a run killed through the new close path (or with `runner.STOPPING`
  set, as before) is "stopped with ergostat". Any other non-zero exit while closing keeps its code.
- **Main merged (lesson-7): not done as a merge.** `git merge main` was refused in this container, as in round 2. I
  ported main's changes to the files this branch touches by hand, so that they match main's:
  `inbox/stats.py` (`one()` takes a `note`; the dismissal's note is carried into it, tested in the dismissal test),
  `inbox/entries.py` (`asks` keeps the note), `inbox/interventions.py` (the alarm remedy's words), `tests/conftest.py`
  and `tests/test_interventions.py`. Main's other changes do not touch these files: the redesign memory and bench,
  `itemindex.py`, `demo_check.py`, dev/ and SPEC's redesign paragraphs. Main's redesign memory reads "dismissed with
  the owner's reason" from model changes, not from modelling requests, so I expect no conflict, but I have not checked
  that by merging. **The merge and the suites after it are left to the factory.**

Each new test was seen to fail with its fix disabled (lesson-9): the tries reset, `part()` falling back to the whole
model, `approvable` with each half forced true, and the plain `--deny` display. Lesson-1: `requests.answer` reads the
request's state and then writes, with no lock between, like the other inbox answers. Suppose `sync` moves the request
in that gap, for example reopening it on a new version. Then the owner's answer still lands after it, and the owner's
answer is the one meant. I wrote no test for that gap.

Budget: about 108 net lines in ergostat/ and diagram.js, within 250. Run here, each file alone: `test_inbox.py`,
`test_modelling_core.py`, `test_modelling_core2.py`, `test_modelling_template.py`, `test_interventions.py`,
`test_notify.py`, `test_runner_and_state.py`, `test_self_improve.py`, `test_leases.py`, `test_spec_engine.py` and
`test_spec_mcp_explain.py`. All pass, and ruff is clean. Not run: the whole suite, the browser files
(`test_inbox_page.py`), and anything after a real merge of main.
