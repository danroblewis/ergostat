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
