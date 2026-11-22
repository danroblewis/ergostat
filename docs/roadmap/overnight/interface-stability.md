# interface-stability: count how often each system's interface changed over the model's recorded history, and say it in `explain system.NAME`
depends-on: []

The architecture proposal (`docs/proposals/architecture.md` §5, *Not computed*) and GAPS' "System architecture
review" *Left* list it: "interface stability over the model's history". Today each system's interface is worked out
(`Spec.interface`, `ergostat/spec/ir.py:928`) and never kept. The model's history (`ergostat/history.py::note`)
records `model.changed` with part fingerprints and a version. It records no interfaces, so nothing can count how
often a boundary's crossings changed. What exists and is NOT rebuilt: `Spec.interface`/`_interfaces`; the
`interface` note in `spec/architecture.py::interfaces` (unchanged); `history.note`'s fingerprint/version logic;
the rule that `model.changed` is never pruned (`store.py:458`, `segments.py:993`).

## Definition of done

1. **A signature per system.** `ergostat/interface_history.py::signature(ports) -> str` hashes (sha256, 16 hex
   characters) an unambiguous canonical encoding of the ports: `json.dumps(sorted([p["dir"], p["kind"], p["part"],
   sorted(p["peers"])] for p in ports), separators=(",", ":"))`. Strings are never joined with a separator. Peer
   order and port order do not change the signature. A different `dir`, `kind`, `part` or any peer does change it.
   `signatures(spec) -> dict[str, str]` gives one signature for each system in `spec.systems`, with an empty
   interface hashed like any other.
2. **Recorded on each model.changed.** When `project.model.spec` is not None (a YAML model), `history.note` adds
   `"interfaces": signatures(spec)` to the event's data. It also records an event when the interfaces differ from
   the last event's, even if the parts and the version are the same. Such an event adds `"interfaces_changed":
   [system names whose signature differs, or which appear or disappear]`. A TOML model (spec None) records no
   `interfaces` key, and its behaviour is otherwise unchanged.
3. **One starting record, not a change.** Suppose the last `model.changed` event has no `interfaces` key, the model
   now has a spec, and nothing else differs. Then `note` records one event with `"baseline": true` and the
   interfaces. `history.changes` leaves out baseline events, as it leaves out `first`. A second `note` on the same
   model records nothing. A TOML model never records a baseline.
4. **Counted over the history, failing closed.** `interface_history.stability(events, system, now_sig) -> dict`
   reads the `model.changed` events **in `seq` order**, never by `time` (lesson-2):
   - **The run** is the longest trailing sequence of events whose data has an `interfaces` dict containing a string
     signature for `system`.
   - **What starts the count over:** an event without the `interfaces` key, an event whose `interfaces` lacks the
     system, or a value that is not a dict or not a string. The run starts after any of these; nothing before it is
     counted (lessons 3 and 5).
   - **Duplicates:** consecutive events in the run with equal `(version, signature)` count as one version (a
     duplicate written by two concurrent `note` calls).
   - **The result:** `versions` (deduplicated entries in the run), `changed` (adjacent deduplicated entries whose
     signatures differ), `unchanged` (trailing deduplicated entries whose signature equals the newest) and `since`
     (the `time` of the first of those, for display only).
   - **Nothing to count:** if the run is empty, or `now_sig` (the signature of the spec as it is now) differs from
     the newest signature in the run, it returns `{"recorded": False}` and gives no counts.
5. **Said where systems are explained.** With a project, `explain system.NAME` (`spec/explain.py::Explainer.system`)
   adds one line after the In/Out ports. Either `Interface over the model's recorded history: unchanged over the
   last U of V recorded versions (since YYYY-MM-DD); C changes.` or `Interface over the model's recorded history:
   the interface as it is now is not recorded yet.` Without a project it adds no line. The words say "recorded
   versions": only versions ergostat loaded are seen. Read errors are not caught and turned into "unchanged".
6. **`ergostat status --since`** lists an interface-only change as `~interface:NAME` for each name in
   `interfaces_changed` (`cli/status.py`). A baseline event is not listed.
7. **Docs current.** SPEC §4a, after the `explain system.NAME` sentence: the stability line, what it counts ("recorded
   versions", what starts the count over). SPEC's `model.changed` description (near line 1720): `interfaces`,
   `interfaces_changed`, `baseline`. `docs/proposals/architecture.md` §5: move stability from *Not computed* to
   *Computed today*. `docs/GAPS.md`: remove "interface stability over the model's history" from *Left*. Not shown
   on the system box or panel (`fold.py` has no project); the docs say only `explain`.
8. **The usual done.** Unit suite and the four browser files pass with rc 0 and no page test skipped for want of a
   port. Ruff is clean. origin/main is merged in and the suites run again. No example is touched (if one is,
   `demo_check` passes on it).

## Files to touch

- `ergostat/interface_history.py` (new): `signature`, `signatures`, `stability`, `said`
- `ergostat/history.py`: `note` records `interfaces`, `interfaces_changed` and `baseline`; `changes` skips baseline
- `ergostat/spec/explain.py`: the line in `Explainer.system`
- `ergostat/cli/status.py`: `~interface:NAME` in `--since`
- `tests/test_interface_stability.py` (new)
- `docs/SPEC.md`, `docs/proposals/architecture.md`, `docs/GAPS.md`

## Risks

- **lesson-3 (failing open):** an event without `interfaces` (a TOML stretch, a spec not loaded, history from
  before this branch), a system missing from an event, a malformed value, or a current model not yet recorded could
  be read as "unchanged". Each starts the count over or gives `recorded: False`. In particular A, [no key], A must
  not read as "unchanged over 2".
- **lesson-5 (stale state under a reused id):** a system removed and made again under the same name would inherit
  its old run. Absence starts the count over.
- **lesson-2 (wall time):** sorting by `time` would misorder events whose clocks went back or are equal to the
  second. Order by `seq`; `since` is display only.
- **lesson-1 (check then write):** `note` reads the last event and then writes without a lock, so two processes can
  record the same version twice. This already happens today and is not fixed here. Counting deduplicates
  consecutive equal `(version, signature)` entries, so a duplicate cannot inflate `versions`.
- **lesson-8 / lesson-9 (a claim wider than the code; a test that can't fail):** a signature that ignores
  direction, kind or peers, or joins strings ambiguously, would pass a test that only adds a part. The signature test
  changes each field one at a time and includes a collision case. The explain wording says "recorded versions",
  never "never changed".
- **lesson-4:** no new number multiplies processes, threads, calls or money; not applicable.
- **lesson-7:** merge origin/main and rerun the suites; tests that count `model.changed` events
  (`tests/test_reload_in_place.py`, `tests/test_reload_soak.py`, `tests/test_runner_and_state.py`) must still pass.
  On a fresh project no baseline is written, because the first event already carries interfaces.
- **lesson-13:** a suite failure unrelated to this change is reported, not fixed in the branch.

## Acceptance tests

All in `tests/test_interface_stability.py`. For each test, the report states the change to the code it guards that
was made, and that the test then failed.

- `test_signature_changes_with_each_field`: from one base port list, changes `dir`, then `kind`, then `part`, then
  one peer (replaced), then adds a peer, each alone; each signature differs from the base and from the others. It
  fails if any field is left out of the encoding.
- `test_signature_ignores_order_and_is_unambiguous`: shuffled ports or peers give the same signature. `part
  "stock.a,b"` with no peers and `part "stock.a"` with peer `"b"` give different signatures. It fails under a naive
  `",".join`.
- `test_note_records_each_systems_interface`: a YAML model in `tmp_path` with two systems; `note` stores
  `interfaces` with both names, each equal to `signatures(spec)`.
- `test_note_records_an_interface_only_change`: `signatures` is monkeypatched to return a different value for one
  system, with parts and version unchanged. `note` records an event with `interfaces_changed == [that system]`;
  without the patch, a second `note` returns None. It fails if `note` compares only parts and version.
- `test_an_old_record_gets_one_baseline_and_it_is_not_a_change`: an existing `model.changed` with the current parts
  and version but no `interfaces`. `note` records one event with `baseline: true`; `history.changes` leaves it out;
  a second `note` returns None.
- `test_a_toml_model_records_no_interfaces_and_no_baseline`: the TOML project fixture; `note` twice gives one event
  with no `interfaces` key. It fails if a baseline is written on every load.
- `test_counts_changes_and_the_unchanged_run`: synthetic events A, B, B, B with distinct versions give `versions 4,
  changed 1, unchanged 3`.
- `test_an_event_without_interfaces_starts_the_count_over`: A, B, [no `interfaces` key], B with `now_sig` B gives
  `versions 1, changed 0, unchanged 1`. A, [no key], A gives `versions 1`. It fails if events without the key are
  skipped rather than starting the count over.
- `test_a_system_removed_and_made_again_starts_over`: A, [interfaces without the system], A gives `versions 1`.
  Also a malformed value (a number or a list in place of the dict or string) starts the count over.
- `test_order_is_by_seq_not_time`: A recorded with `at=200`, then B with `at=100` (a later seq), `now_sig` B. It
  gives newest B, `changed 1, unchanged 1`. It fails if events are sorted by `time`.
- `test_a_duplicate_record_is_one_version`: A(v1), A(v1), B(v2) gives `versions 2, changed 1`. (v1,A), (v1,B), an
  interface-only change, gives `versions 2, changed 1`.
- `test_the_model_as_it_is_now_unrecorded_is_said_not_counted`: no events, or a newest signature different from
  `now_sig`, gives `{"recorded": False}`. The explain line then says "not recorded yet" and has no counts.
- `test_explain_system_says_its_interface_history`: a YAML project. `note`; then a crossing is added by editing the
  file, the model is reloaded, and `note` again. `explain system.NAME` holds "unchanged over the last 1 of 2
  recorded versions" and "1 changes" for the edited system. An untouched system reads "unchanged over the last 2 of
  2". `explain` without a project has no "Interface over" line.
- `test_status_since_lists_an_interface_change`: an interface-only `model.changed` event shows `~interface:NAME` in
  `ergostat status --since 1h`; a baseline event is not counted as a change.

## Size budget

130 net lines of code outside `tests/` and `docs/`: `interface_history.py` about 75, `history.py` about 25,
`explain.py` about 15, `status.py` about 5, with 10 to spare.

## Notes from the plan review (answer each)

- An interface-only model.changed (parts and version unchanged) can only come from a change in how ergostat computes Spec.interface, e.g. after an upgrade, so 'C changes' and '~interface:NAME' would count changes that are not model edits (lesson-8). State this in SPEC §4a and the model.changed description, or handle it explicitly in this branch.
- Define interfaces_changed only when the previous model.changed event has a valid interfaces dict; otherwise a parts change after an event from before this branch lists every system as appeared and status shows ~interface for all of them. Add a test.
- test_explain_system_says_its_interface_history: a crossing between the edited system and the 'untouched' one changes both interfaces; the added crossing must not touch the untouched system's ports, or the '2 of 2' assertion cannot hold. Name the crossing in the report.
- signature() must raise on a port missing dir/kind/part/peers (no .get defaults, lesson-3), and at least one test must use ports from a real Spec.interface, not only hand-built dicts, so the assumed field names are checked.
- status --since must skip baseline events through history.changes or an explicit check; the status test's baseline event must differ in parts from the event before it, so a status that only compares parts would wrongly list it and the test would fail.
- Fix the '1 changes' wording (singular/plural) and assert the exact string.

## Where it stopped

Built in round 1; nothing left. These choices were made alone and are the most reversible ones:

- **Wording.** "1 change" / "C changes", and "1 recorded version" / "V recorded versions", as the plan review
  asked. The test asserts the exact `"); 1 change."` ending, so item 5's "C changes" applies to every C except 1.
- **`interfaces_changed`** is written on any YAML `model.changed` (a parts change too) whose previous event has a
  readable `interfaces` dict (a dict of strings), and only when the list is not empty. When the previous event has
  none, it is left out and no system is listed as appeared
  (`test_a_parts_change_after_an_old_record_lists_no_interface_change`, an extra test).
- **Baseline.** It is written when the previous event's `interfaces` is missing *or* unreadable, and parts and
  version are the same. A malformed record is read the same way as one from before this branch.
- **Upgrades.** The plan review's first note is answered in the docs: an interface-only change, with parts and
  version unchanged, comes from how ergostat works out interfaces. SPEC §4a and the `model.changed` description say
  so. It is not handled any other way.
- **The explain test's crossing.** `wa` (in `a`) reads `stock.outside`, which is in no system. Only `a`'s ports
  change, so `b` reads "2 of 2".

**After the factory's unit run failed.** Its tail stopped at 77% with no failure shown. Every test file was then run
again on this branch, one batch at a time. The only failure was `tests/test_spec_engine.py::
test_a_sensor_s_command_is_told_how_to_call_ergostat_back` (`KeyError: 'ERGOSTAT_PROJECT'`). It passes alone, twice.
It is a race in the test, not in this branch (lesson-13): the sensor runs `env | grep ... > env.txt` every 0.5 s, and
`run_for` reads `env.txt` right after `Engine.close()`. A run that began just before the close can have truncated the
file. That code path never reaches `history`, `explain` or `interface_history`. No code was changed for it; it
belongs in its own gap.

**Round 2.** No review findings were given. Main (a7cad540) is merged in (f242720c), and no code changed after
that. On the merged head these were run one at a time, each rc 0: `tests/test_interface_stability.py` (15),
`tests/test_reload_in_place.py`, `tests/test_reload_soak.py` and `tests/test_runner_and_state.py` (55),
`tests/test_architecture.py`, `tests/test_graph_cli_web.py`, `tests/test_spec_systems.py` and
`tests/test_spec_engine.py` (57). Ruff is clean. The full unit suite and the four browser files are left to the
factory's watched run. Net code is 77 lines, inside the budget of 130.

**After the factory's second unit run failed.** Its tail stopped after 30 dots, before any percentage, with no
FAILED or ERROR line. The run was cut off; no test failed it. The tail does not show why, and this session cannot
find out: both the watched parallel run (`suite_watch.py ... -n 8`) and a watched serial run were refused here. So
every unit file (all but the four browser files) was run serially on 940c4627, in batches, and none failed: 435,
384, 336, 364 (1 xfailed), 290, 245 and 212 passed. On top of those, 134 passed in the explain, status and
architecture batch, plus the 15 acceptance tests and the reload and runner files (11, 1 and 43). The skips are
platform skips (the macOS sandbox, remote and container tests). Ruff is clean. No code was changed, because no test
fails and so nothing in this branch needs fixing. If the run is cut off again, the watchdog's own report (threads,
memory, or one worker past 2 GB) will name the cause. That report is not in the tail given.

**After the factory's third unit run failed.** Its tail stopped mid-line at 91%. It shows no FAILED or ERROR line,
and no closing JSON line from `suite_watch.py`, which that script prints even when it kills a run. So something
outside the watchdog killed the whole run, the same as the 77% run and the 30-dot run. The three runs stopped at
different points. No code was changed, because no test was shown failing. The watched parallel run was refused again
in this session (`uv run python scripts/suite_watch.py -- uv run python -m pytest -q -n 8 --dist worksteal -p
no:randomly`). Timing `note` on a generated 200-workflow model was refused too. Checked instead: `Spec.interface` is
worked out once per spec and cached (`ir.py:951`), so the work `note` adds is one pass over the parts per load.
The new test file starts no process or thread. These ran serially, rc 0: `tests/test_interface_stability.py` (15),
then `tests/test_scale_caches.py`, `tests/test_runner_and_state.py` and `tests/test_reload_soak.py` together (79,
144 s). The soak test takes 123 s by its own design, two minutes of edits. Ruff is clean. The cause of the kill
(an outer timeout or the container's memory) is not in the tail, so it is left to the factory.

**Round 3.** No review findings were given. Main (e1e778c1) is merged in (921ef55e). That merge left the System
architecture review entry in `docs/GAPS.md` garbled: the branch's old text and main's new text were both kept, one
after the other, and main's *Left* list still named interface stability. It is now one entry: main's text, plus
the interface count under what is done, with interface stability gone from *Left* (item 7). No code changed. This
container has no `origin` remote, so "origin/main" means the local `main`, which HEAD contains. These ran one file
batch at a time, rc 0: `tests/test_interface_stability.py` (15); `tests/test_reload_in_place.py`,
`tests/test_runner_and_state.py`, `tests/test_architecture.py`, `tests/test_graph_cli_web.py` and
`tests/test_spec_systems.py` (101). Ruff is clean. The full unit suite and the four browser files are left to the
factory's watched run.

**Round 4.** The queue's finding was `tests/test_warm.py::test_the_owners_stop_is_said_only_on_the_run_it_stopped`,
which failed in the queue and again alone. On this branch's head (46e77de7, main b9528e0e merged in) it passes alone,
and the whole of `tests/test_warm.py` passes (21, 24 s). This branch does not touch the warm daemons
(`ergostat/daemons/`), the engine's stop path (`Engine.stop_run`) or the test. Its only contact with that test is the
one `history.note(self.p)` call in `Engine.start_all`. That call runs synchronously, before any daemon starts. It adds
one pass over the parts (`Spec.interface` is cached) and writes the same single first `model.changed` as before. The
test's failing window comes later: the stop, the replaced process (`len(starts) == 3` within 5 s) and the `agent.ran`
notes, and none of those reads `model.changed`. So it is reported and left alone (lesson-13). Running it on clean
`main` was refused in this session (`git worktree add --detach /tmp/main-wt main` followed by the test three times),
and so was a five-times rerun loop on this branch. So this session cannot show whether it fails on main too. The
queue's failing output was not given, so the assertion that failed is not known. If it is the 5 s wait for the
replacement process, that is a fixed timeout under load (lesson-10) in the warm code's own gap. No code changed. Ran,
rc 0: `tests/test_interface_stability.py` (15) and `tests/test_warm.py` (21). Ruff is clean.
