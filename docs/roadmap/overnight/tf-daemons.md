# tf-daemons: the ticket factory read and run by daemons

Branch `tf-daemons`, from main (145d00e). Asked by the owner (2026-11-19): convert `examples/ticket-factory` to use
daemons (SPEC §9.7, `docs/DAEMONS.md`), idiomatically, since the example teaches people how to use ergostat. The
owner is running it now with a live record, so the record must still replay.

## Definition of done

**What becomes a daemon.** Sensors that read the same source share one daemon (one per source); a sensor that stands
alone gets an inline daemon; a block whose runs are short and frequent hands them to a daemon; anything clearer as a
one-shot run stays `run:`. Concretely: the three sensors that read the record (`ai-spend`, `repings`, `cycle-hours`)
share one daemon (`measures`), which answers the readings asked at the same moment with one read of the record; the
Jira watcher (`arrivals`) has an inline daemon; the nine short steps (every step but the three AI ones) are handed to
one block daemon (`steps`), each ticket's run on a thread of its own with its own `ERGOSTAT_*` values taken from the
line, never the process's, a `cancel` answered at once; the scripted teammate (every 5 s) has an inline daemon. The
AI steps (`work`, `address`, `fix-ci`) and the daily `reporter` stay `run:`, and the README says why.

**Nothing in the model's structure changes.** Every event type, series name, stock, flow, auxiliary, item kind and
state, block name, goal and parameter is the same, and so is each event's source (the watcher's `ticket.found` is
still recorded as `arrivals.main`), so a record made before replays, and the completion estimates, the modelling loop
and the projections keep working. Only `run:` lines change, to `daemon:` (and the daemons' declarations).

**The engine's socket lists items** (`items`, as `ergostat item --kind K --json` answers), so a daemon reads the
record without starting a process; `bin/tf.py` uses it, and falls back to the command as before.

**Still works:** `factory.conf.example` and online settings (a changed `factory.conf` is read again without a
restart), the stand-in (`AI=standin`), and the README's quick start. The README explains the daemons: which part is
which shape, why the rest stays `run:`, how to restart one after editing `bin/`, and how to try one by hand.

## Acceptance tests

`tests/test_ticket_factory_daemons.py`:
- `test_the_daemons_change_only_how_parts_run`
- `test_each_daemon_answers_lines_piped_by_hand`
- `test_the_daemons_start_fill_their_sensors_and_survive_a_kill` (each daemon killed, restarted by its supervisor,
  and reading again; tickets still move)

`tests/test_calls.py`:
- `test_the_socket_lists_items_as_the_command_does`

Then: the unit suite and the four browser files under `scripts/suite_watch.py` (one at a time, rc 0, no skips for
want of a port), ruff, and `scripts/demo_check.py ticket-factory` three times, all ok. The before/after process
starts, CPU and latency of an offline run, in the report.

## Size budget

**300 net lines** outside `examples/`, `tests/` and `docs/`.
