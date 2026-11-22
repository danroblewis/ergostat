# perf-header-projects-list-is-cheap: The header's project list holds running projects only, worked out off the request path; the CLI's list is unchanged

depends-on: []

Problem: every page load's header asks /api/projects (ergostat/web/static/util.js:356-395). projects.known (ergostat/projects.py:52-78) walks every folder under ~/.ergostat (2,534 on the owner's machine: 1,479 with the repository gone, 1,054 stopped, 1 running) and for each loads the model and takes a snapshot (_row, projects.py:33-49) under one global lock. On the live factory it took 113 s, then 32 s, for 349 KB, holding a worker and the GIL every other answer needs; cold it gave no answer in 120 s. The resulting select has 2,534 options, 2,533 disabled. projects.known is also what `ergostat projects` prints (ergostat/cli/running.py:348), so it must keep listing stopped projects.
Change: (1) projects.known stays as it is for the CLI. A new projects.running() lists only projects whose engine runs (running_pid, web.json), each with its goals-off counts, and a cheap count of the stopped ones (folders counted, no model loaded). (2) the page server works running() out on a background thread every 60 s; /api/projects reads the last list and takes no global lock; a stopped project's model is never loaded in the page server. (3) the header menu lists running projects, then one muted line 'N stopped (ergostat projects)'. Default, no owner question: the switcher drops stopped projects.
Definition of done:
1. With 2,000 fake folders (2 running) /api/projects answers in under 0.3 s, under 20 KB, and loads two models.
2. No model load or snapshot of another project happens inside a request.
3. The menu still switches to a running project and shows its 'N off'.
4. `ergostat projects` still lists stopped projects, with the same rows as before (a CLI test).
Files: ergostat/projects.py, ergostat/web/server.py, ergostat/web/static/util.js (refreshProjects), tests.
Acceptance tests: the 2,000-folder unit test (time, size, rows); the CLI test for 4; a browser check of the menu; on the owner's machine /api/projects under 0.5 s cold (GET only).
Budget: 90 net lines outside tests.

Milestone: pages-answer-fast. Owner items: 2. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. `projects.running()` (ergostat/projects.py) lists the projects whose engine holds `run.pid`, each with
its `known` row (page from web.json, goals off), and counts the stopped folders without loading their models.
`ergostat projects` still calls `known()`, which is unchanged. The page server starts one lister thread per process
(`start_lister` in `serve()`, ergostat/web/__init__.py; `list_projects` in ergostat/web/server.py). It works out the
list at once and then every 60 s, and keeps the last list if a pass fails. `/api/projects` returns that list before
any model or snapshot of its own project is read, and takes no lock. The header (util.js `refreshProjects`) shows the
running projects with 'N off' / 'N unknown', then one disabled line, 'N stopped (ergostat projects)'. The change
also reaches ergostat/web/__init__.py, which is outside the Files list: it is one line there, to start the thread
where the page's other background threads start.
Choices made with nobody to ask (each easy to undo):
- Until the first pass is done, the answer is `{"running": [], "stopped": null, "at": null}`: no stopped count is
  shown rather than a false 0, and the page asks again the next time the reader comes to the menu.
- A running project with no web.json is listed, disabled, as '(no page)'.
- The page's own project counts among the stopped ones when its engine is not running.
- The answer's shape changed from a list to `{running, stopped, at}`.
Tests: tests/test_projects_header.py has the 2,000-folder test (DoD 1 and 2: 2 models loaded by the pass, none and no
snapshot inside the request, under 0.3 s and 20 KB), a failed pass keeping the last list, and the CLI test (DoD 4).
tests/test_page_refresh.py::test_the_header_menu_lists_running_projects_then_counts_the_stopped is the browser check
(DoD 3): the real answer, then a stand-in answer, switching to the other project's page. Each test was seen to fail
when its code was broken: an answer worked out inside the request, stopped projects loaded, the 'N off' dropped.
Not run here: the owner-machine check (/api/projects under 0.5 s cold), the full unit suite, and the other three
browser files.
