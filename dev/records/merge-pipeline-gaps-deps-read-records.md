# merge-pipeline-gaps-deps-read-records: The dependency reader reads the entries from dev/records/

depends-on: [merge-pipeline-gaps-md-regenerated-on-land]

Problem: dev/bin/deps.py:44-70 parses docs/GAPS.md on main for each gap's dependencies and closes. Change: deps reads the same entries through gapsdoc.entries over main's dev/records/ (the helper is added here if merge-pipeline-gaps-intake-reads-records has not landed; whichever lands second reuses it and the reviewer checks there is one). Done: on the pinned fixture deps gives the same dependencies, closes and blocked reasons from the records as from the rendered GAPS.md; an unreadable record is said by name and the gaps it names are treated as blocked, never as free; no test of deps reads the live docs/GAPS.md. Files: dev/bin/deps.py, dev/bin/gapsdoc.py, tests/test_backlog.py. Budget: 40 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
