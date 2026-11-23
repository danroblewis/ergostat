# The owner's list (2026-11-22), verbatim in substance

Decisions already made by the owner today:
- Use "goal" instead of "loop" for what is held or off: "when I open the 'loops' page I know it actually means 'goal', like 'what do I want to get done', and it's weird that it's called loops". The Loops page becomes Goals. "Feedback loop" and "control loop" stay for the structures.
- The modelling system's own goals come out of the headline (shown beside it).
- The owner explicitly asks for a Dashboard page and an Agent show page below. These are the owner's own requests and override the earlier "no new pages" rule for these two.

1. Items page: some states mean an item is no longer interesting (for gaps: dead, closed). Hide them by default, with a way to show them. URL query parameters already exist (e.g. /items?kind=gap&state=closed&view=graph); the default should leave terminal states out. Clicking a filter should not reload the page.
2. Loading times on several pages are very slow at times (they do eventually load). Maybe dataset size, maybe the web server is busy and requests queue, maybe something else. (The live factory page is the large case.)
3. The "frontier" checkbox on the Items page seems to do nothing.
4. It's unclear what "collapse done" means; which states are "done"?
5. Diagram page: after changing renderer parameters and toggles, flow lines sometimes connect to nothing, perhaps because several passes of positioning and path finding leave them pointing at an old location.
6. The Blocks diagram has MIMO vector connectors (many-to-one, one-to-many: several signals bundled onto one line and unbundled elsewhere). Wanted in the Dynamics diagram as well.
7. The Dynamics diagram allows drag-and-drop of parts, but the lines are not updated until a refresh.
8. The Diagram page uses only two colours, which makes it hard to read. Standard technical-diagram practice: a second tone of each colour (lighter, darker or more transparent) for non-critical lines and information links. The boxes around system groups are bad in the same way: technical diagrams draw only the corners as short lines, or corners with a lighter connecting line, or something else. Something else is needed.
9. Diagram page: the right sidebar's default (background clicked) shows broken loops, suggestions, graphs, a list of feedback loops and an explanation of symbols. Most are useless: make it the explanation of symbols, or at least that first.
10. Diagram layout rendering takes far too long, maybe worth rewriting entirely. With "Flows only" on, it should be possible to rearrange and reposition items so that the flow of an item is clear and obvious: perhaps a "re-fit" or "re-arrange" button.
11. The Items page is hard to understand; the heading for an item type is hard to find.
12. Items page, Graph view: the graph now holds items of different kinds related to each other, notably in the "knowledge" system. It contains gaps and reviews; reviews seem to belong to the knowledge system, but gaps certainly do not, so it is unclear why they are there.
13. Items page: every item type's list section closed by default.
14. Items page: "show all" exists when a list is long, but there is no real pagination, so the problem returns right after clicking it.
15. Items page: no page representative of an item type. Wanted: the whole picture of an item type: its definition, the stocks and flows related to it, the feedback loops and control loops it takes part in, a well-designed filter, "what all is this item?"
16. Dynamics page: when items have active leases owned by a valve, the valve's sidebar should show those items.
17. Items page Gantt chart cannot predict the real timeline: it stacks every gap as far left as possible, as if 100 gap runs start at once. We have a system dynamics model and a control model; a small simulation should give a real estimate of what finishes when and in what order.
18. A Dashboard page: the information the owner cares about exists but is spread over pages (scrolling on Items, panning and zooming on the Diagram). A configurable set of panels, each configurable, each showing something from other pages: a list of items of a kind, a list matching a filter, a graph of counts of a kind over time, a stock (possibly populated externally), several flow rates on one graph, an X/Y plot of one measure against another, projections, a nodes-and-edges diagram, a Gantt chart, a heatmap. Half dashboard, half analysis: "the dashboard is an analysis".
19. Agents page: view an AI agent's prompt files (rendered markdown); for program runners, the program (syntax highlighted); for narrow AI, its specification; for decisions, the means of deciding; for rules, the rule patterns. An Agent show page.
20. Item show page (e.g. /item/gap%2Fregression-guarantees-proposal): very good and has the right information. Wanted: if the item was leased to agents, the subset of the Dynamics and Blocks diagrams it passed through; short fields laid out in a flowing way to save width; the "history (N changes)" parts could go (useful, though). The "contexts" (append) section needs a lot of work: it nests to the right, renders nested markdown in tables, and most of the page ends up as markdown on the far right. Designers should find the problem and fix it.

The owner: "Don't just turn each of these into individual tickets. Think about them, reason about them ... determine which ones are large projects and need more planning, which are simple tasks and can be done soon, schedule planning if it's needed, increase parallelism, and build a new graph of gap tasks."
