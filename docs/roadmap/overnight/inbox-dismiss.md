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
