# Factory decisions, 2026-11-22

After the token surge the factory had a large backlog, little direction, and several faults that kept recurring. These are the decisions taken to bring it to a good working state. Each is marked **done**, **in progress** or **next**.

## Keep it running

1. **A switch waits for the old engine to exit.** Done. `run --stop` gave up after 10 s, so a start could see a closing engine as running and start nothing. Every reverted switch took about 24 s, and every clean one 10 s or less.
2. **A new version gets 300 s to show it is healthy.** Done.
3. **The factory reads its whole record.** Done. `fac.items` lists each state on its own, so a record past 500 items is no longer read in part.
4. **Sensors that crash are fixed, not tolerated.** Done for the two that failed on every read.
5. **An outage is not the work's fault.** In progress: a stopped AI account pauses the runs (`an-ai-usage-limit-stop-pauses`) instead of parking what was running. The same is wanted for Docker being away.
6. **Docker's file handles stop growing.** In progress: suites copy their checkout into the container, then sessions do the same. Until then the handle count is watched and Docker is restarted before the limit.
7. **Raise the Mac's open-file limit** as a margin. It does not replace the fix in 6.
8. **No live-only patches.** Done for the stopgaps of this run. A fix to the live instance goes to main in the same sitting, so a switch cannot lose it.

## Keep main good

9. **Main is pushed only after the full queue passes,** with any flake passing twice by name.
10. **Browser tests run daily on main.** Next (`merge-pipeline-browser-daily-on-main`). They are off in the queue until that job exists.
11. **Finish before starting.** Approved work lands before new work is favoured. The batch goes from 3 to 4 while the queue's wait is over its goal.
12. **Stacked branches** remain the way to raise merge throughput. In progress.

## Organize the work

13. **Development moves to milestones.** In progress (`milestone-*`). Every gap belongs to one, one or two are active (never more than three), a completed milestone never reopens, and single gaps may be pulled forward.
14. **Repairs live in a weekly Upkeep milestone,** outside the limit, so they neither wait nor hold a milestone open forever.
15. **A continued gap replaces the gap it continues.** Done: 44 gaps that waited on an abandoned gap now wait on its continuation, and 28 superseded gaps are closed.
16. **The graph shows every dependency.** In progress (`graph-draws-every-dependency`).
17. **The research and plans are kept in the repository,** in `docs/research/2026-11-22-design-and-planning/`. Done.

## The first milestones

1. Factory runs reliably
2. See the work: graph, Items page, item and kind pages
3. Goals
4. Dashboard
5. Agent page
6. Diagrams
7. Timeline and forecasts
8. Complexity
9. Remote systems and compute
