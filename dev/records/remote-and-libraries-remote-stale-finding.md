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

## Where it stopped

Built as defined (round 2). remote-stale is raised when status.json has read_ok False, which `readings.answer` sets only
when the readings request gets no answer. A single reading refused as stale, untimed or in the future inside an answered
request leaves read_ok True, so it gives no remote-stale finding; only that sensor's `sensor.failed` reports it. Round 1
found that SPEC §4c and AGENT-GUIDE §3a step 4 said more than this. Of the two fixes it offered, this round takes the
more reversible one: both texts are narrowed to "its readings request fails" and say that a stale refusal is not this
finding. Making stale refusals set read_ok False would change readings.py and the box's "not answering" state, both
outside this gap's Files. Left for a gap of its own if wanted: raise remote-stale for readings refused as stale.
Round 1's non-blocking finding is fixed: the "N old" age now comes only from a reading's time (`read`), not from the
model's `answered` time. The "none of its measures has been read here" branch is tested.
