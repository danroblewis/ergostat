# remote-and-libraries-remote-stale-finding: check and the Check page say remote-stale when a remote's readings fail

depends-on: []

Problem: remote-systems.md §5 says stale or failing readings give 'remote-unreachable and remote-stale findings' on the Check page and in `check`. Only remote-unreachable exists, raised when the model fetch fails (ergostat/remote/compose.py:180-188). When the model answers but its readings fail or are refused as stale (ergostat/remote/readings.py:198-204; status read_ok False, ergostat/remote/cache.py:108-116) only the status's attention says so (ergostat/remote/__init__.py:40); `check` is silent.
Change: compose adds a `remote-stale` finding from the same status the box reads.
Definition of done:
1. When a remote's status has read_ok False (and its model did answer), compose adds a finding `remote-stale` on system.NAME: 'remote NAME: its readings fail (WHY) since T; its measures here are N old'. With read_ok True or never read, none.
2. remote-unreachable and remote-stale are never both given for one remote at one load: unreachable wins.
3. SPEC §4c lists remote-stale with the other finding codes; AGENT-GUIDE §3a step 4 says what to do (the remote answers but its sensors there are not reading: tell its owner).
Files: ergostat/remote/compose.py, docs/SPEC.md, docs/AGENT-GUIDE.md, tests/test_remote.py.
Acceptance tests: test_remote_stale_finding (status planted with read_ok False: check gives remote-stale; set True: gone); test_unreachable_wins_over_stale.
Size budget: 50 net lines.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
