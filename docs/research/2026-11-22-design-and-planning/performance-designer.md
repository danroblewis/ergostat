# Owner item 2: slow page loads (performance designer, 2026-11-22)

**Verdict.** The client is not the cause. The server is: it queues work, and the queue is filled by a few things the
page asks for. The data size matters in one place, the per-snapshot refold of moved items. Payload size matters only
over the tunnel. "Very slow at times, they do eventually load" is a queue. While a burst is being worked off, every
request waits behind it, static files included. When the burst ends, the pages are fast again. My measurements agree
with the performance engineer's (`plan/performance-engineer.md`) on every cause. I reuse that file's gap names so the
two sets merge, and I add the user-side pieces: what the page says while it waits, the payloads trimmed to what is
drawn, and page speed modelled as an upkeep goal with a budget test.

## What a user sees (GET only on :8798; a copy of its state served on :8850; the large demos)

- **The live factory at its worst.** A request for `/static/style.css`, which needs no work at all, waited **228 s**,
  then the connection was reset (the factory restarted itself for a drain at 04:46). `/api/status` gave nothing in
  120 s. The server held **84 sockets in CLOSED** and 5 in CLOSE_WAIT. These were requests whose clients had hung up,
  still queued and still to be computed. run.log has 191 "the client went away" lines, and each one is an answer
  that was built in full and then thrown away. The worst bursts were at 02:23 and 15:xx.
- **The live factory, fresh after the restart.** I sampled it every 15 s for 6 min while the other designers browsed.
  `status` took 0.03 to **15.6 s**, `style.css` up to **10.6 s**, and there were up to 26 open connections at once.
  `/api/projects` took **113 s** once and 32 s the next time, for 349 KB: 2,534 rows, of which 1,479 are errors
  (repositories gone), 1,054 are stopped and 1 is running.
- **The copy, with no engine and one browser** (`plan-perf-8850_*.png`):
  - Diagram content after about 1.4 s (`status` 1.3 s). The first `graph` answer is **1.5 MB** for two closed
    boxes. 1.1 MB of it is `causalLoops` and 309 KB is `corr`.
  - Items: 0.8 s.
  - **Loops: 97 `loop-control` requests fired at once**, network idle after **9.4 s**. The page also fetches
    `graph?open=*`, 2.5 MB, for its sparklines.
  - Item page: polls the item every 6 s. Each poll is 181 KB (history 86 KB, record 54 KB) and costs 1.4 to 2.3 s.
- **The copy under load** (`perf/load.py`: k tabs polling status, graph, items and loops):
  - 1 tab: graph p50 2.5 s.
  - 4 tabs: everything p50 about 1 s, max 3 s.
  - 10 tabs: p50 2 to 3 s, max 5.4 s, and `style.css` up to 2.2 s.
  One tab already keeps the server near saturation, because the shared snapshot costs 1.3 s and expires after 1.5 s.
- **The large demos** (8796, 8797): most answers come back under 0.1 s. The exceptions:
  - `projects` 4.3 to 5.8 s on every page load;
  - big's Loops page: `loop-control` requests queue up to 3.2 s;
  - the values-only diagram poll: 2.2 s.
- **The client.** No long main-thread tasks on Diagram, Loops or Agents. Every slow page was waiting on the network.
  Layout time on the Diagram is owner item 10 (the diagram-render cluster) and is a separate cost.

Screenshots: `shots/plan-perf-live-diagram-1s.png`, `plan-perf-live-diagram-10s.png`, `plan-perf-live-loops-idle.png`,
`plan-perf-8850_*.png`, `plan-perf-8796_*.png`, `plan-perf-8797_*.png`.

## Why (with the code)

1. **One queue, no shedding.**
   - `PooledServer` (web/__init__.py:28) has 24 workers fed by an unbounded `queue.Queue`.
   - A job is run even when its client has gone.
   - Static files and 1 KB answers wait in the same FIFO as 100-second ones.
   - The engine runs in the same process (cli/running.py:117), so it shares one GIL.
2. **Bursts the UI itself creates.**
   - The Loops page fans out one `loop-control` per goal (pages.js:46): 97 on the factory, repeated every 5 min per
     tab. The server serialises these behind `control_api.WORKING`, so up to 24 workers sit waiting on one lock.
   - `Live.keep` clears the whole answer cache once it holds more than 16 entries (server.py:128). The burst
     therefore evicts its own results and everyone else's.
   - The header's project switcher calls `projects.known()` on every page load (util.js:362). That loads the model
     and takes a snapshot of every stopped project on the machine, refreshed every 10 min, under one global lock.
3. **Every answer waits for a fresh snapshot.**
   - `Live.snapshot` keeps it for 1.5 s, but it costs 1.3 s idle and 5 s or more under load. So nearly every poll
     rebuilds it, or waits for someone else's rebuild.
   - Most of the cost is `state.explain` → `items.moved` → `_late` refolding every item that moved since the last
     reading. Each refold scans segments with a Python per-row type test before it checks whether the item is in the
     segment at all (segments.py:136, 436).
   - Answers that never read the snapshot still build it: `projects`, `messages`, `actions`, `inbox`.
4. **Payloads larger than what is drawn.**
   - `graph` sends every causal loop (1.1 MB) even when only two closed boxes are drawn.
   - The header's `status` poll (131 KB every 5 s per tab) carries all loops (63 KB) and the model check (54 KB). The
     header needs only the count of goals off.
   - Loops pulls 2.5 MB of graph for sparklines.
   - The item page re-sends 181 KB every 6 s.
   - Nothing is gzip-compressed. The 1.5 MB graph compresses to 50 KB, which matters over the tunnel.
   - The ETag is computed after the answer is built, so a 304 saves bytes but no work.

## Judgement: owner, review and intent

- **They agree.**
  - R8 says "never blank; the old drawing stays, dimmed, until the next is ready".
  - Q11 says panels show "Loading…".
  - R6 piece 5 and Q60 say forecasts are present on first paint.
  - All three need answers that do not wait. A page that serves the last snapshot and says how old it is fulfils
    both the owner's request and R8. None of the filed quick fixes makes anything faster; they make waits visible.
- **No new UI.** Page speed becomes an upkeep goal of the modelling system: answer time and queue depth are sensors,
  and "pages answer within 2 s" is a goal. Its evidence is the existing goal evidence panel. Today's decision puts the
  modelling system's own goals beside the headline, not in it, so this costs the headline nothing.
- **Conflicts.**
  - The Dashboard (owner item 18) multiplies panels. Each panel must read shared, background-computed answers, never
    one request per panel per poll, or it repeats the Loops fan-out. The dashboard gaps should depend on
    `perf-answers-never-wait-for-a-snapshot` and `perf-loops-page-asks-once`.
  - R12/R1 may remove the Loops page. Its fan-out is still worth fixing now, because the same per-goal analysis is
    what a box's control panel (R1) will need.
- **The project switcher** is a design defect as much as a performance one. A select holding 2,534 projects, 2,533
  of them disabled, helps nobody. It should list running projects only.

## Proposed gaps (summary)

1. **perf-web-requests-never-pile-up** (incremental): drop a queued GET whose client left; bound the queue; static
   files and cheap answers in a fast lane; a run.log line for each slow answer; the page aborts its fetches when it
   is left.
2. **perf-answers-never-wait-for-a-snapshot** (incremental): the snapshot is kept fresh in the background and served
   with its time; answers that do not use it skip it; the model-file check leaves the request path.
3. **perf-segments-item-span-first** (quick): check the item's span before testing types; same answers, about 37%
   off each snapshot.
4. **perf-header-projects-list-is-cheap** (incremental): running projects only, worked out off the request path.
5. **perf-loops-page-asks-once** (incremental): one summary answer for all goals, computed in the background; an LRU
   answer cache; sparklines from `series`.
6. **perf-answers-carry-only-what-is-drawn** (incremental): gzip; causal loops on demand; a light header status; the
   item page polls only what changed.
7. **perf-the-page-says-how-old-it-is** (quick): "as of 04:51:03 · updating" when an answer is older than its poll;
   never blank.
8. **perf-page-speed-is-an-upkeep-goal** (incremental): sensors and a goal in the modelling system, plus a budget
   test (requests, bytes and p95 per page on a factory-size fixture).
9. **perf-snapshot-counts-without-refolding** (incremental, one owner question).
10. **perf-page-server-process-proposal** (large, proposal first): the page server out of the engine's process.

Order: 3, 1, 4 and 5 can run in parallel at once. Then 2, then 6 and 7. 8 needs 1. 9 comes after 3. 10 comes after
the rest are measured. Overlaps:
- Q11 `gap/ui-open-into-and-every-panel-link-show-that-somethi` and Q36
  `gap/ui-the-address-holds-what-is-selected-and-the-windo` are complements; 7 builds on Q11.
- R6 piece 5 and Q60 `gap/ui-the-finish-estimate-is-a-clock-time-that-agrees` depend on 2.
- R8 pieces 1 and 5 agree with 7.
- R12 and R1 bear on 5.
