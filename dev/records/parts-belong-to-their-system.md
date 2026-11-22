# parts-belong-to-their-system: a part knows which system it belongs to, and is shown without the system's name where that system is known

depends-on: [remote-of-remotes-continued]

The owner, 2026-11-22: "systems should be namespaced, if a thing belongs to a system it should get prepended with the system name, we can remove the system name from the thing's name if we know the system's name."

Today composed names are made by joining strings (`f"{inst}-{bare}"` in `ergostat/library/expand.py:492,560`, `f"{remote}-{n}"` in `ergostat/remote/compose.py`). Nothing records the owner of a name, so a local `m-a-open` and remote `m`'s `a-open` can only be told apart by bookkeeping in each place, and a diagram inside system `m` repeats `m-` on every box.

## Definition of done
1. The compiled model records, for each part made by a library instance or a remote, the system it belongs to and its name within that system. A hand-written part in no such system records none.
2. Full names do not change: every existing model, event, record and reference keeps working, with no migration.
3. Where the system is known (a diagram or list inside that system's box, or its system page), the part is shown by its short name, with the full name on hover and in links. Where it is not, the full name is shown. Two parts shown side by side never read the same.
4. The short name is derived from the recorded owner, never by stripping text that happens to match.
5. SPEC says what a part's system and short name are.

## Files to touch
`ergostat/library/expand.py`, `ergostat/remote/compose.py`, the compiled model, the web payload and diagram labels, `docs/SPEC.md`, tests.

## Risks
- No new page or panel: only labels change.
- lesson-3: a part whose owner is unknown shows its full name.
- After any label change, run `tests/test_diagram_rendering.py`.

## Acceptance tests
- a library instance's part and a remote's part each record their system and short name
- a hand-written `m-a-open` beside remote `m`'s `a-open` keeps distinct owners
- inside a system's box the short name is shown, with the full name available; outside, the full name
- an existing example compiles to the same full names

## Size budget
200 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. 127 net lines of code outside `tests/`, `docs/` and `dev/` (`git diff --numstat main HEAD`).

- The record: `ergostat/spec/belongs.py`. A library instance (`library/uses.py`, from `expand.py`'s new
  `Made.shorts`) and a remote (`remote/compose.py`, `parts()` now yields each part's name there) give each part a
  copy of its `where` carrying `Belongs(system, short)`. The compiler copies them into `Spec.belongs`, keyed
  `stock.NAME`. Name-making lines are unchanged, so full names are the same.
- The labels: `ergostat/shown.py` adds `shown` to nodes and to box rows and ports in the fold output (the Control
  and Dynamics views); `diagram.js` and `dynamics.js` draw `shown || label`. Clashing short names fall back to
  full names.
- Acceptance tests: `tests/test_parts_belong.py` (7 tests) and
  `tests/test_diagram_rendering.py::test_inside_its_own_systems_box_a_part_reads_by_its_short_name_with_its_full_name_on_hover`.
  Each guarded piece was broken in turn and the test caught it: owner check in `shown.py`, the clash rule, the
  remote record, the nested-use record, `nameOf`, and `fullOnHover`.

Choices made with nobody to ask, the most reversible taken each time:
- "Full name on hover": the page has a tested rule that no diagram part has a tooltip
  (`NO_TOOLTIPS`, `test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip`). A first version that
  used `<title>` failed that test, so instead the part's own text switches to its full name while the pointer is on
  it. Its panel and every link still use the full name (`label` is unchanged).
- The Blocks and Process views are left as they were (full names): their labels are math symbols and item kinds,
  not part names. The title of an open system's outline still shows the system's full name.
- No owner is recorded for a remote's stand-in (a part it does not serve), a `once: true` template's parts, a
  name a parameter gives whole, or an instance's own system unless it is nested. All of these show full names
  (lesson-3).
- "Hand-written `m-a-open` beside remote `m`'s `a-open`": this clone's main has none of `remote-of-remotes-continued`
  (no record, no names-taken handling), so a remote part whose composed name a local part already took is still
  the existing defined-twice error. The test checks this at the loader: the hand-written part records no owner
  and the remote's other parts record `m`. It also compiles a hand-written `m-b-open` beside remote `m` and checks
  that it records no owner.
- No origin/main in the clone. Local `main` (5617e225) is the parent of the definition commit, so there was
  nothing to merge.

Tests run (serial, one file at a time): `tests/test_parts_belong.py`; `tests/test_templates.py`,
`tests/test_remote.py`, `tests/test_remote_box_measures.py`; `tests/test_remote_lines.py`,
`tests/test_library_trust.py`, `tests/test_library_provenance.py`; `tests/test_spec_systems.py`,
`tests/test_dynamics_view.py`, `tests/test_correspond.py`; `tests/test_graph_cli_web.py`,
`tests/test_remote_pair.py`, `tests/test_upkeep_template.py`: all pass. `tests/test_diagram_rendering.py` in full
under the watchdog with Playwright: 201 passed, rc 0, none skipped. An earlier full run (with the `<title>`
version) had one more failure, `test_every_lines_panel_links_to_the_parts_it_joins[coordinator]` ("link corrected
opened nothing", 5 s wait). It passed twice alone and in the full rerun, and both parts it links are hand-written,
so this change does not relabel them. It is not fixed here (lesson-13). Not run here: the whole unit suite, the
other three browser files, `demo_check` (no example changed).
