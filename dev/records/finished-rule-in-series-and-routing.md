# finished-rule-in-series-and-routing: The process map, the state counts over time and message routing take their finished states from the one function, with their outputs proved unchanged or the change said

depends-on: [items-kinds-say-which-states-finish]

Problem: items-kinds-say-which-states-finish moves the finished rule into finish_of for the Items page, the dependency graph and the estimates, and leaves three other callers on their own rules: ergostat/process.py:75-83 (done_states, also stripping 'leased'), ergostat/series.py:338 and 371-398 (state counts over time) and a separate done_states in ergostat/messages/route.py:39. Until they agree, the Items page can call a state finished that the process map draws as a middle state, or that a message's done route does not treat as done.
Change: each of the three is read and compared with finish_of on every demo spec and the factory-shaped fixture. Where its set equals finish_of's (after its own stated extras, such as stripping 'leased'), it calls finish_of and keeps the extra as one named line. Where it differs on purpose (message routing's done may be a different idea: where a message's answer goes), it keeps its rule, is renamed so it no longer reads as the same thing (e.g. route_done_states), and one SPEC sentence says how it differs. Any change in output is listed in the PR per demo and kind.
Definition of done:
1. No function named done_states remains outside ergostat/spec/finished.py and spec/itemindex.py's inference that finish_of wraps.
2. A parity test: the process map's answer, /api/series state counts and message routing's targets are byte-identical before and after on the six demos' specs with seeded records, except for the differences listed in the PR.
3. SPEC says in one place which uses share the rule and which does not, and why.
Files: ergostat/process.py, ergostat/series.py, ergostat/messages/route.py, ergostat/spec/finished.py, docs/SPEC.md, tests/test_finished_states.py.
Acceptance tests: the parity test; a unit test per caller on a kind with declared done, inferred done and one state.
Budget: 70 net lines.

Milestone: items-page-readable. Owner items: 4 (one answer to 'which states are done', everywhere). From the owner's list and the design review of 2026-11-22.
