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
