# Owner item 2: slow page loads (performance engineer, 2026-11-22)

Short answer: it is the server, not the client and not the bytes. Every answer waits for a shared state snapshot that
takes 1.3 s on the factory's record with nothing else running and 5 to 15 s under load. That snapshot expires after
1.5 s, so nearly every poll waits for a new one. The web server shares one Python process (one GIL) with the engine.
Some page loads fan out more requests than the 24 worker threads can serve, and requests are never cancelled, so work
for clients that have hung up piles up in an unbounded queue. On the live factory this had built up until the page
server stopped answering: `/api/status` gave nothing in 120 s, or in 580 s, while `/` (a static file) came back in
0.7 s. Most data sizes are fine because the Items page already pages its list; two payloads are wasteful (below).

## What was measured (GET only on :8798; profiles on a copy of its state)

**The live factory, wedged (pid 9278, up 4 h 07 m, 2.4 GB RSS, 165% CPU, 96 threads).**
- `/` came back in 0.69 s. `/api/status`, `/api/items`, `/api/graph?view=dynamics` and `/api/graph?view=blocks` gave
  nothing in 120 s each, and a second `/api/status` gave nothing in 580 s.
- The process held 66 sockets in CLOSED and 10 in CLOSE_WAIT: clients had given up and the server was still working on
  their requests.
- A native `sample` showed most threads in `__psynch_cvwait` (waiting for the GIL, 785 `take_gil` frames). The CPU went
  to `inflate_fast` (zlib: event segment blocks being decompressed again) and `PyUnicode_Splitlines` (segments.py:421-424).
- Its run.log has 195 "the client went away" lines. In one hour, 48 of them are `/api/loop-control`, plus 15
  `/api/items-flow` and 12 `/api/series`: these are the fan-outs (below).
- The process was restarted by a drain switch at 04:46. Nothing I did caused that.

**The live factory, fresh (pid 92817, 4 min old), each API asked in turn:**
- `status` 13.3 s; `projects` gave nothing in 120 s; `items` (unfiltered, 2.4 MB) 30.8 s; `systems` 5.6 s; `fit` 55 s.
- Everything else answered in 2 ms to 0.55 s, because each of those hit a snapshot less than 1.5 s old.

**Page loads in Chromium, GET only, no clicks** (`plan-prof/net.py`):
- **/diagram**: content after 2.5 s (`status` 2.3 s). The first `graph` answer is 1.47 MB; the values-only poll is
  242 KB and took 7.8 s.
- **/items**: content after **16.5 s**. The page's own HTML took **4.6 s**, because it queued behind the Diagram
  page's requests that were still running. Then `status` took 8.5 s, `items?per_kind=25&shown=1` (222 KB) 7.4 s, and
  `projects` (349 KB) 7.9 s. The 23 `items-flow` requests, one per kind, all came in under 0.4 s.
- **/loops**: about **60 `loop-control` requests at once**, one per goal. They run one at a time behind
  `control_api.WORKING` and finish between 0.2 and 7.6 s. That is more requests than there are worker threads, so
  `loops` 4.6 s and `status` 4.8 s waited behind them. The page also fetches `graph?open=*`, **2.4 MB**, only to draw
  the stocks' sparklines.
- **/agents**: content after 0.9 s; the next poll of `agents` took 4.9 s.

**The large demos (:8796, :8797, :8791):** most answers come in under 0.1 s, with spikes when a snapshot is rebuilt:
- `projects` 3.8 s;
- ticket-factory `items?per_kind=50&shown=1` 4.3 s and `systems` 8.7 s;
- `items-graph` 4.5 MB on ticket-factory.

The demos' records are small, so the factory is the only case that shows the problem fully.

**Profiles on a copy of the factory's state** (`ERGOSTAT_HOME` pointed at a copy made with `sqlite3 .backup`, no
writer running):
- `state.snapshot` takes 1.25 to 1.6 s on one thread.
- Every API answer costs the snapshot plus 0.1 to 0.6 s of its own work. `fit` costs 7.3 s, `projects` 14 s (it
  loads 2,534 project folders) and `systems` 3.4 s.
- Inside the snapshot, **2.5 of 3.5 s (profiled) go to `state.explain`**. The chain is `explain` → `counted`
  (state.py:99, with `at=t1`, the stock's last reading) → `items.moved` (spec/items.py:279) → `_late`
  (spec/items.py:220). That folds again, from the record, every item that changed since that reading: **1,754 items
  in 88 calls on every snapshot**. Each fold is a `segments.query` by item.
- Within that, `Segments._rows` (segments.py:436) tests every segment's types (2.1 M calls of the `_types_matcher`
  lambda, segments.py:136) before it checks whether the item is in the segment at all.
- What two changes would save, measured:
  - checking the item's span first: **1.25 s to 0.79 s**, with the same answers;
  - matching `where` as the items are now instead of as they stood at the last reading: **0.35 s**, but that changes
    what the counts mean (a question for the owner).

## Why it behaves as the owner says ("very slow at times; they do eventually load")

1. **Every answer waits for a fresh snapshot.** `Live.snapshot` (web/server.py:151-180) keeps a snapshot for 1.5 s.
   `_answer` builds or waits for one before it dispatches (server.py:446), even for answers that never read it
   (`projects`, `guide`, `messages`, `actions`, `inbox`, `report`). Polls come every 2.5 to 5 s, so almost every poll
   finds the snapshot stale and waits for a whole rebuild. The rebuild is shared, which is good, but it costs 1.3 s
   alone and 5 to 15 s against the engine. Hence "at times": answers are instant just after a rebuild and slow just
   after an expiry.
2. **One process, one GIL, shared with the engine.** `cli/running.py:117-126` starts `serve()` and `Engine` in the same
   process (266 sensors, 37 machine blocks). The engine's CPU and the page's CPU compete for one core.
   docs/proposals/scale.md #15 names this but measured only synthetic N.
3. **Pool starvation by fan-out, and no cancellation.**
   - `PooledServer` (web/__init__.py:28-50) has 24 workers and an unbounded `queue.Queue`. A job whose client hung up
     is still run. Each "went away" line marks work done for nobody.
   - The Loops page sends one `loop-control` per goal (pages.js:45-51; also review.js:304), about 60 at once. Each holds
     a worker while it waits on `control_api.WORKING`, so one Loops visit fills the pool and the next page's HTML
     waits (the 4.6 s for `/items`).
   - The page scripts never abort a fetch when a page is left (there is no AbortController).
4. **The shared answer cache is too small.** `Live.keep` (server.py:128-132) clears the whole cache once it holds more
   than 16 entries. The Loops page's 60 per-goal analyses each add one, so every 17th throws away the `numbers`,
   `models` and `fit` entries along with the rest, and those are rebuilt.
5. **`/api/projects` loads every project on the machine.** `projects.known` (projects.py:52-78) walks 2,534 folders
   under `~/.ergostat` (most are test leftovers; 923 have a `web.json`). For each it loads the model and takes a
   snapshot of the record, under one global lock, with rows kept for 60 s (running) or 600 s (stopped). The header
   asks for it on every page load (util.js:356-395). It is the slowest single answer (more than 120 s cold, 349 KB),
   and while it runs it burns the GIL that every other answer needs. Stopped projects are shown disabled in the
   menu, so loading their models buys nothing.
6. **Model files checked on the request path.** `Live.get()` → `Settled.due()` → `model.stamp`
   (model.py:569-592) re-parses all 25 YAML files every 10 s (`INCLUDES_EVERY`) on whichever request comes first:
   0.5 s alone, 1.9 s profiled. scale.md lists it as found but not fixed.
7. **Payloads (secondary).** On localhost the bytes cost little. JSON encoding is under 0.1 s even for 1.5 MB. Nothing
   is compressed, though, and the tunnel (<the tunnel host>) carries every byte. The waste:
   - `graph?open=*` (2.4 MB), fetched by Loops for sparklines;
   - `projects` (349 KB);
   - `items-graph` (0.97 MB on the factory, 4.5 MB on ticket-factory);
   - the Diagram's first `graph` (1.47 MB) and its 242 KB values-only poll every 2.5 s.
8. **The client is not the cause of these waits.** Every slow page above was waiting on an API answer. Diagram layout
   time is owner item 10 (the diagram-render engineer's cluster) and adds to this only on /diagram.

## The fixes, in order of value per line

| Gap | Size | What it removes |
|---|---|---|
| perf-segments-item-span-first | quick | 37% of every snapshot (1.25 s to 0.79 s), with identical answers |
| perf-answers-never-wait-for-a-snapshot | incremental | the wait in every poll: the last snapshot is served while the next is built; answers that never read it skip it; the model-file check leaves the request path |
| perf-web-requests-never-pile-up | incremental | work for clients that left; a bounded queue; a run.log line for each slow answer (waited, worked, path), which is the evidence the wedge lacked |
| perf-header-projects-list-is-cheap | incremental | the slowest answer (more than 120 s, 349 KB): load only running projects, off the request path |
| perf-loops-page-asks-once | incremental | 60 requests per Loops visit, the 2.4 MB graph for sparklines, and a 16-entry cache that flushes itself |
| perf-snapshot-counts-without-refolding | incremental (one question) | the rest of the snapshot's cost (0.79 s to about 0.35 s) |
| perf-compress-large-answers | quick | about 10x fewer bytes over the tunnel for answers over 64 KB |
| perf-page-server-process-proposal | large: proposal first | the GIL shared with the engine: the page server in its own process, or reading a snapshot the engine publishes |

Overlaps with filed gaps:
- Q11 (`gap/ui-open-into-and-every-panel-link-show-that-somethi`) and Q36 (`gap/ui-the-address-holds-what-is-selected-and-the-windo`)
  make the waits visible ("Loading…"). They are complementary and make nothing faster.
- Q60 (`gap/ui-the-finish-estimate-is-a-clock-time-that-agrees`) and R6 piece 5 ("computed with the page load and
  cached per window, present on first paint") depend on answers not waiting on the snapshot. perf-answers-never-wait
  makes them achievable.
- Q09 (`gap/ui-an-unknown-address-gives-a-page-with-the-navigat`) stops one needless poll, a small piece of the same
  idea.
- No filed quick fix does any of the above. docs/proposals/scale.md #12 and #15 are extended: #12's "the header's own
  status poll" is covered by perf-answers-never-wait, and #15 by the proposal gap.

Risks:
- Serving a snapshot a few seconds old: the page already shows values up to 1.5 s old plus the poll interval. Bound
  it (at most 15 s, or the age the page shows), and never for `at=` (a past moment).
- Dropping a job whose client left: the check must never drop a POST that has been read (only GETs, before work
  starts).
- The projects list showing fewer projects: stopped ones are already disabled in the menu.
- The Loops perf column filled later (it says "being worked out").

Housekeeping, not code: `~/.ergostat` holds 2,534 project folders. `ergostat compact --projects` exists for the
orphans, and the Supervisor could run it. That is a write outside the page, so I did not do it.
