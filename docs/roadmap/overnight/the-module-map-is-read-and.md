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
