# module-map-race: knowledge.module_map reads, writes and prunes its sha-keyed cache without racing other sessions
depends-on: []

## Definition of done
- knowledge.module_map (dev/bin/knowledge.py:167) no longer checks is_file() and then reads in two separate steps: it reads in one try and rebuilds the map when the file is missing or its JSON is partial, so a file deleted or half written by another process is never an error.
- The cache is written to a temp file in the same directory and then renamed into place with os.replace, so a reader never sees partial JSON.
- Pruning never deletes the file for the sha just read or written, and a file another process has already deleted (FileNotFoundError on unlink or stat) is skipped, not raised.
- A session start, a lease, or backlog.py never fails because of the module map cache; the leases seen ending with FileNotFoundError on run/modules/<sha>.json (gap/redesign-rescored-as-the-record-moves-continued, 11-21 18:52) cannot happen again.
- The agent guide notes that the cache is safe for concurrent use.

## Acceptance tests
- tests/test_knowledge.py::test_module_map_survives_its_cache_file_removed_between_check_and_read (monkeypatch: delete the file after the existence check)
- tests/test_knowledge.py::test_module_map_rebuilds_on_a_partial_cache_file
- tests/test_knowledge.py::test_module_map_prune_skips_a_file_already_gone_and_keeps_its_own

## Size budget
30 net lines

## Where it stopped

The factory's unit run after b6381b41 showed one `F` at about 28%, but its tail was cut off before the summary, so the
failing test is not named. The session was refused when it tried to run the whole unit suite (under suite_watch), to
read logs outside /work and to commit through a heredoc. One file at a time, every file that covers the change passes:
test_knowledge.py with test_factory_knowledge.py (78 passed), test_factory.py (116 passed, 2 skipped), test_backlog.py
(19), test_factory_resources.py (10), test_factory_sessions.py (5) and test_code_health_coverage.py (11). The new
`mtime` helper collides with no name in knowledge.py. No code changed in this round: without the test's name, no cause
is known. The one F may be a load flake unrelated to this change (lesson-13). The next round needs the failing test's
name from the queue's full log.

After the second unit run (its tail cut off again, at 74%, with no failure shown): the likely cause is the branch's own
test file. tests/test_knowledge.py loaded knowledge.py (and with it `fac`) at import, so every xdist worker collected it
and kept `fac` and `knowledge` in sys.modules. test_factory.py's `sys.modules.setdefault("fac", ...)` and
`sys.modules.get("fac") or ...` then picked up that leftover, so failures depended on test order. The file now loads
both per test in a fixture under monkeypatch.setitem, so nothing is left behind. No code outside tests changed. This is
inferred, not seen: the failing test is still not named. test_knowledge.py followed by test_factory.py in one process:
119 passed, 2 skipped.

Round 2 answers the three findings of review 1. (1) An in-place write passed every test: the partial-file test now
patches os.replace and checks it is called once, from a temp file in the same directory, while the cache still holds
the old partial text, and that the result is the map; writing in place fails it (seen). (2) A session killed between
mkstemp and os.replace left `.<sha>.*.tmp` for ever: the prune now removes those (matched by that name only) once older
than ten minutes, so a live write, seconds old, is never taken; a new test shows a stale one removed and a fresh one
and an unrelated `.notes.tmp` kept; dropping the age check fails it (seen). (3) mkstemp's 0600: the temp file is set to
0644 (fchmod) before writing, the most reversible choice (the umask cannot be read without setting it, which is racy
across threads); the partial-file test checks the mode, and removing fchmod fails it (seen). The queue's "browser failed
and named no test" and "first failing merge of a batch of 2" carry no test name and no log is reachable from /work;
this branch touches no browser or ergostat code (only dev/bin/knowledge.py, its test and the agent guide), so nothing
was changed for them (lesson-13). Size: dev/bin/knowledge.py is +31 -6 against main, 25 net, within the budget of 30.
