# remote-and-libraries-explain-remote-parts: explain names a remote's parts and the loops that cross into a remote

depends-on: []

Problem: remote-systems.md §6: 'Loops are found through remote parts ... explain names the remote parts on it'. ergostat/spec/explain.py:141-157 (feedback) lists every loop with no remote marking, and neither a part's nor a system's explanation (explain.py:389, :495) says a part is a remote's, where it runs or how old its readings are, although docs/AGENT-GUIDE.md §3a tells agents to use `ergostat explain system.incidents` to look before referencing. remote_of (ergostat/remote/__init__.py:9) and box (:61) already know it.
Change: explain says remoteness wherever it names a part.
Definition of done:
1. Explaining a part that remote_of names starts with 'remote NAME's (runs at URL, model vM, read T ago | not answering)', from remote.box, and for a block says it is never run here.
2. explain system.NAME for a remote's box system says the same once, then its served systems and parts as today.
3. In the feedback list, a loop with any remote part ends with ' (crosses remote NAME: part, part)'; a goal's explanation whose loop reads a remote part says the remote's part is a measured input there (a disturbance or a setpoint handed to us), never an actuator.
4. The MCP explain tool returns the same text (it calls explain), and nothing changes for a model with no remotes (the existing explain tests pass).
5. AGENT-GUIDE §3a step 2 says what explain shows.
Files: ergostat/spec/explain.py, docs/AGENT-GUIDE.md, tests/test_remote.py.
Acceptance tests: test_explain_marks_remote_part (a planted remote, explain of stock.incidents-open names the remote and its version); test_explain_loop_crossing_remote (a local goal whose controller's flow drives a remote stock that drives a local one: the loop line names the remote's parts); test_explain_without_remotes_unchanged (golden text of a demo model unchanged).
Size budget: 80 net lines.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
