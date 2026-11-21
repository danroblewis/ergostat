# groomer-remembers-removed-links: a dependency the coordinator removed is not proposed again

depends-on: []

On 2026-11-21 the groomer proposed that `architecture-reviewer` wait on two gaps. The coordinator removed both, because the definition's own list of what it reuses names neither. Thirty minutes later it proposed the same two again. Every grooming run starts with no memory of what was refused, so each bad link costs an approval every run.

## Definition of done
1. `backlog.py refuse-link GAP DEPENDS_ON --why TEXT` records the pair in `run/backlog/refused-links.jsonl`.
2. `backlog.py propose` drops a recorded pair from `links_add` and lists it among its refusals, with the recorded reason.
3. `backlog.py dep add` on a recorded pair still works and clears the record: an explicit decision overrides it.
4. The groomer's prompt says a new link must name the line of the waiting gap's definition that needs the other gap.

## Files to touch
`dev/bin/backlog.py`, `dev/prompts/groomer.md`, `tests/test_backlog.py`.

## Risks
- lesson-3: an unreadable record file refuses nothing and says so; it never stops a proposal.

## Acceptance tests
- `tests/test_backlog.py::test_a_refused_link_is_not_proposed_again`
- `tests/test_backlog.py::test_an_explicit_dep_add_clears_a_refused_link`
- `tests/test_backlog.py::test_an_unreadable_refusal_file_stops_nothing`

## Size budget
30 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. Choices made without anyone to ask, each the most reversible:

- `propose` had no proposal to drop a link from, so it takes an optional `FILE` (`propose [FILE]`): the proposal as
  `check()` leaves it, printed as the groomer's diff, with nothing written. Without a file it is unchanged. The same
  drop applies where proposals actually flow: `groom` (the proposal put to the coordinator) and `apply FILE` (by the
  groomer). It does not apply to changes by hand (`dep add`).
- The record file is append-only, one JSON line per decision. In file order a later line wins. `dep add` of a recorded
  pair appends `cleared: true` once the link is applied, so a `dep add` refused for a cycle keeps the refusal. Nothing
  is rewritten. A missing file refuses nothing and says nothing. A file that cannot be read or parsed refuses
  nothing, and the proposal's refusals carry a line saying so (lesson-3).
- lesson-1: `dep add` reads the record and then appends without a lock. A `refuse-link` written in between is
  overridden by the clear, which is the later, explicit decision either way.
- dev/README.md lists the two new commands. That file is outside the list of files to touch, but the house rule says to
  keep the agent guide current.

Size: 33 net lines in dev/bin/backlog.py (42 added, 9 removed) and +2 in the groomer's prompt. That is 3 lines over,
from the new subcommand's argparse lines and the optional FILE for `propose`. I kept them as plain lines rather than
packing them tighter.
