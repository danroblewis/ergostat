# perf-web-requests-never-pile-up: The page server drops requests whose client left, bounds its queue, keeps a fast lane for cheap answers and logs each slow answer

depends-on: []

Problem: on 2026-11-22 the live factory's page server (pid 9278, 165% CPU, 2.4 GB) stopped answering: /api/status gave nothing in 580 s and /static/style.css waited 228 s. It held 66-84 CLOSED and 5-10 CLOSE_WAIT sockets: requests whose clients had sent their GET and gone, still queued. PooledServer (ergostat/web/__init__.py:28-50) has 24 workers fed from one unbounded queue and runs every job however long it waited; static files wait in the same queue. run.log has about 195 'the client went away' lines (48 in an hour from /api/loop-control), each an answer built for nobody, and nothing records queue wait or work time. No page script aborts its fetches when the page is left.
Change: (1) detecting a client that left: a worker takes the job before the request is read, and a client that sent its GET and then closed still has its request bytes waiting, so a peek before reading returns those bytes, not b''. So the handler first reads and parses the request line and headers (as it does now), and only then, before calling _answer for a GET, checks the socket: select() says readable and recv(1, MSG_PEEK | MSG_DONTWAIT) returns b'' means the client sent FIN: drop the job and count it. (A pipelined second request gives bytes, not b'', and is served.) A GET that waited in the queue more than 60 s is dropped too. A POST that has been read is never dropped. macOS has no POLLRDHUP, so nothing relies on it. (2) the queue is bounded (256); past it new connections get 503 with Retry-After: 2. (3) static files, / and answers that need no snapshot go to a fast lane of 4 workers the API queue never fills. (4) every answer over 2 s writes one run.log line: 'web: slow GET /api/x: waited 4.1s in the queue, 3.0s working, 77 KB'; counts by path are kept in memory and carried by /api/status as `web` when any was slow in the last 10 minutes. (5) util.js apiText aborts a page's in-flight fetches (AbortController) when its page element leaves the document.
Definition of done:
1. A client that sends a complete GET and then closes before a worker is free (the measured CLOSE_WAIT case) is never handed to _answer.
2. With all API workers blocked, /static/style.css answers in under 200 ms and the 257th queued connection gets 503 at once.
3. A slow answer writes one line with queue wait and work time.
4. No read POST is ever dropped.
5. Leaving a page cancels its in-flight fetches.
Files: ergostat/web/__init__.py, ergostat/web/server.py (the check before _answer, timing in do_GET), ergostat/web/static/util.js, tests for the web server, one browser test.
Acceptance tests: a unit test that opens a socket, sends a full GET, shuts down its write side and closes while every worker is busy: _answer is not called for it (on macOS and Linux); 24 slow requests (5 s each) plus 30 whose clients send and hang up after 1 s: the server does the work of the 24 only and the log names them; unit tests for 2-4; a browser test for 5.
Budget: 140 net lines outside tests.

Milestone: pages-answer-fast. Owner items: 2. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. All five points are done, with the acceptance tests in tests/test_web_lanes.py and
tests/test_page_polling.py::test_leaving_a_page_cancels_its_fetches_in_flight.

Overrun reason: 172 net lines against 140. The lanes need the request's path before a worker takes the job, and nothing reads it at that point, so a small reception thread (one selector, ergostat/web/__init__.py `_reception`) holds each connection until its first bytes arrive, peeks at them and queues the connection by path. That is about 40 of the lines. It also means a browser's idle, pre-opened connections no longer tie up a worker each.

What was built, and the choices taken without asking (each easy to undo):
- The fast lane takes GETs of /static/*, the page's own addresses (/, /items, ...) and /api/projects. Every /api answer in `_answer` takes the snapshot except items-query (a record graph query, not cheap) and the proposal graph, so the only answer that "needs no snapshot" is /api/projects (the header's cached list). It is now answered before the snapshot is taken. /file/* stays in the API lane, because it can read up to 20 MB.
- The fast-lane queue is bounded at 256 too. Connections still waiting for their first bytes are capped at 512 (503 past that) and closed after 10 s of silence (the handler's own timeout). The listen backlog is raised from the standard 5 to 128: at 5, the acceptance burst of 54 connects waited 1-3 s on SYN retries, so the hang-ups arrived only after workers were free.
- A 503 reads what the client sent before closing, so the close sends FIN and not RST, which would discard the answer.
- "Over 2 s" means queue wait plus work. A dropped GET writes one line too ('web: dropped GET /api/x: the client left after 3.1s in the queue', or 'too old'), and its count goes in `web.dropped` beside `web.slow`. `web` appears only when something was slow in the last 10 minutes. The counts come from the newest 2,000 slow-or-dropped records.
- Aborted fetches: the header's own fetches (status, projects) are passed `kept` and belong to no page. A fetch of a page that has left never settles, so its page draws nothing and logs no error.
- The drop check runs only on the pooled server: the mTLS remote listener (its own server class) is unchanged.
- SPEC does not describe the page server's pool or /api/status's fields, so it needs no change. This gap is not in docs/GAPS.md.

Not run here: the other three browser files (test_diagram_rendering, test_items_page, test_page_refresh), the full unit suite and demo_check (no example touched). The 54-connection test and the 200 ms test are marked serial and are timing-bound. On macOS they were not run: this clone is Linux only.

### Round 2: the review's four findings

Overrun reason: about 215 net lines against 140 (raw diff of ergostat/, comments included): round 1's reception thread (about 40) plus round 2's guards around it (about 45), which the review asked for so one bad connection or a socket past 1023 cannot stop the server answering.

- Blocking, left() and fds of 1024 and up: select() is gone. left() peeks with recv(1, MSG_PEEK | MSG_DONTWAIT) alone, with the socket's timeout set to 0 for the peek and then restored. Without that, Python waits out the handler's 10 s timeout before any recv, whatever the flags, and every GET took 10 s longer (seen when the first version of this fix failed three tests). A reset is "gone". Any other error means the server cannot tell, so the GET is served (lesson-3). Tests: test_left_works_on_a_socket_numbered_past_1024 (a socket numbered 1100 with a 10 s timeout: alive, pipelined bytes, FIN, closed) and test_a_get_on_a_connection_numbered_past_1024_is_answered (descriptors filled up to 1024, so the server's accepted socket is numbered past it; the test asserts that it was and that the GET was answered). With round 1's left() put back, both fail with "ValueError: filedescriptor out of range in select()".
- Lesson-1, the hand-over of new connections: `_new` is now a queue.SimpleQueue. process_request puts, and the reception gets until the queue is empty, so no connection can land in a list that was swapped out. No test puts a competing write in the gap: the swap is gone, so there is no gap left to test.
- The unguarded reception loop: each step (taking a new connection, routing one with bytes, closing one held too long) runs in `guarded`. An exception there logs 'web: reception closed a connection: ...', closes that connection only, and the loop goes on. A failing select() is logged and retried. Test: test_a_reception_step_that_raises_closes_that_connection_only (cheap() raises for one path: that client gets a close, and the next request is answered). Without the guard it fails, because the next client times out.
- The waker: the socketpair's sending end is non-blocking, so the comment is true. server_close's own send now catches the error a full buffer raises. The same test asserts getblocking() is False.
- The non-blocking finding from the other gap (docs/GAPS.md:234, a-reviewer-in-the-modelling) belongs to that gap's entry, not this one, and is left alone.

Run in round 2: tests/test_web_lanes.py (11 passed), tests/test_web_access.py (26 passed), tests/test_page_polling.py with Playwright under suite_watch (18 passed, rc 0, none skipped), and ruff (clean). Not run: the full unit suite, the other three browser files and demo_check (no example touched). Nothing to merge: main has not moved since the clone.

### Round 3: main merged in

Main (2a97eafb2781) conflicted in the three web files, and the branch now holds it. Each side's change is kept:
- `server_close` calls main's `stop_lister(self)` and then the branch's stop of the reception and both lanes.
- /api/status keeps the branch's `web` field on main's new answer.
- `refreshProjects` keeps the header's `kept` fetch (it belongs to no page, so it is not aborted) and main's re-ask when the list is not ready yet (`ps.at == null`).
- Main now answers /api/projects from its lister at the top of `_answer`, before any snapshot. That makes the branch's own early `projects` answer (which called `projects.known()`) dead code, so it is removed. The fast lane still takes /api/projects, and it is still cheap: main's answer reads the lister's last list and takes no lock.
No review findings were listed for this round other than the merge conflicts, so nothing else changed.

Run in round 3, after the merge: tests/test_web_lanes.py (11 passed), tests/test_web_access.py (26 passed), tests/test_projects_header.py (6 passed), tests/test_page_polling.py with Playwright under suite_watch (20 passed, rc 0, none skipped, 897 s), and ruff (clean). Not run: the full unit suite, the other three browser files (test_page_refresh among them, which reads /api/projects) and demo_check (no example touched).

### Round 4: main merged in again

Main (7cb97857e338) conflicted only in tests/test_page_polling.py: main added test_the_loops_page_asks_once_for_every_goal where the branch added test_leaving_a_page_cancels_its_fetches_in_flight. Both tests are kept, unchanged. No other finding was listed, so no code changed.

Run in round 4, after the merge: tests/test_web_lanes.py (11 passed), tests/test_web_access.py (26 passed), tests/test_projects_header.py (6 passed), tests/test_page_polling.py with Playwright under suite_watch (21 passed, rc 0, none skipped, 951 s), and ruff (clean). Not run: the full unit suite, the other three browser files and demo_check (no example touched).

### Round 5: an aborted page fetch settles

Overrun reason: unchanged from round 2 (about 215 net lines against 140). This round's fix is 3 net lines fewer in ergostat/: the try/catch around the fetch goes, a 2-line pageLeft and handler come in, and review.js gets one guard.

The finding (util.js:343 with review.js:298-311): an aborted page fetch returned a promise that never settled, so no caller's finally ran. availLoops left availBusy true after Model was left mid-fetch, so later visits never got their loop summaries.
- apiText no longer swallows the abort: the left page's fetch rejects with the browser's own AbortError, so every caller's finally runs. `pageLeft(e)` (util.js) says whether an error is that one.
- A rejection that no caller catches is not reported: a window "unhandledrejection" handler calls preventDefault for an AbortError. The choice taken without asking (easy to undo): reject, rather than give availLoops a cleanup of its own, because any other try/finally around a page fetch had the same leak. The cost: a caller's catch now runs for a left page and may write its error text into that page's elements. Those elements are no longer in the document, so nothing is shown (route() closes the detail panel before it aborts).
- availLoops returns from its catch on pageLeft(e) without writing an error into AVAIL, which outlives the page. Its finally resets availBusy.
- Test: tests/test_page_polling.py::test_leaving_the_model_page_mid_fetch_and_coming_back_fills_whats_available holds loops?perf=1, leaves Model for Agents, comes back, and asserts that the summaries are asked for again and fill the Loops table with no page error. With round 4's never-settling promise put back, it fails (no second ask, 60 s timeout). With the unhandledrejection handler removed, both it and test_leaving_a_page_cancels_its_fetches_in_flight fail on a page error ('signal is aborted without reason').

Nothing to merge: main is at the branch's last merge (ead497d1).
