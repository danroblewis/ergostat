# ergostat: the design review

From the design lead, 2026-11-22. Sources: sixteen reviews (eight designers, each blind and then briefed), the 46 user stories in `stories.md`, the eight story-test reports in `story-results/`, and the screenshots they cite in `shots/`. Everything proposed stays inside the owner's decisions: no new page or panel, two diagrams each true to its discipline, recognised diagram types only, items are not tickets, systems are namespaced, large systems matter, people only read except for the gated actions.

How the stories fared, tested by newcomers on the running demos: of 46, **18 were not possible at all**, **none was both fully possible and obvious** (A3 on a desktop and F1 came closest), and the rest were possible only in part or only for someone who already knew where to click.

## 1. Executive summary

### What a newcomer gets wrong today, and why

Every blind reviewer, asked what ergostat is, wrote some form of: *an operations console for pipelines of AI agents, for an operator who knows control theory, and it seems to be struggling with itself.* All eight corrected this after reading the intent: it is a model of any running system, laid over the tools a team already has, read two ways, for engineers and product managers alike, and people mostly read it. The interface is what misled them, in five ways.

1. **The first screen says nothing about the system.** The home is the folded diagram, which the owner calls the control panel. Folded, a system is an empty box that says "28 feedback loops inside" (`story-0-a1-home.png`, `story-4-big-home.png`). No description, no goal, no value against a bound, no health. The answer to "is it healthy?" is in a side list and on another page.
2. **The loudest thing is ergostat's own upkeep.** The `modelling` system is drawn first; its two goals are off in every demo and are all or most of the red headline; on big its 24 identical requests fill the list (`story-0-a2-home.png`). A newcomer learns that the tool's own feedback fails.
3. **The one place a person acts cannot be read.** There is no Inbox. Requests are machine text cut off with "…", mixed with alarms, in a list that re-sorts under the pointer, with inputs labelled "how ma" and a pointer to a command line (`story-4-job-home.png`, `story-4-typed-lost.png`).
4. **The two perspectives are not named, and above the leaf neither is true to its discipline.** The switch says "Dynamics / Blocks". "Loop" means two different things in one panel. The top of Blocks is a column of unconnected "Q" boxes (`story-7-h1-blocks.png`); the Dynamics view of the product draws none of its goals and 18 overprinted loops named by their paths (`story-6-g3-dyn-product.png`). The expert notation, which is good, starts two or three levels down.
5. **The numbers and the words contradict each other.** One flow has three rates; a panel says an actuator "never opened" beside what it "moves"; a goal reaching its target on schedule is as red as one failing; group headings on Agents read "0 person" above two people. Each one costs trust in everything else.

### The five changes that matter most

1. **Make the closed system box the control panel** (R1). Description, then one row per goal: value, bound, trend, a status word, where it is heading. The folded diagram then answers "what is this, is it healthy, where do I look" on its own, on a phone too.
2. **Put the system first and ergostat's upkeep apart** (R2). `modelling` is drawn last and labelled, counted apart in the headline, listed after the system's goals, and made to hold in the demos.
3. **Turn "Needs attention" into the Inbox** (R3). Three fixed groups; each request a plain sentence with Approve and Deny that say what they answer; a list that holds still; requests alike folded; one step from every page.
4. **Make each diagram true to its discipline at every level** (R4, R5). Blocks: a real loop at the top (references, summing junction, controller and plant subsystems, feedback), a function in every block, one loop per row. Dynamics: every goal drawn as goal-seeking structure, a handful of loops named by mechanism, doubt drawn on the part.
5. **One truth for each fact, in words a person can repeat** (R6, R7, R11, and about thirty quick fixes). A goal is a "goal"; "off", "approaching" and "flapping" are different words; a forecast is a sentence; one rate per flow with its window; the evidence for a goal agrees with the Record and reads as a runbook; every mention of a goal leads to it.

### Three decisions for the owner

- **"Goal" in place of "loop" for what holds or is off** (R11). It changes `docs/vocabulary.md`, where "Loop (holding, off)" is deliberate. Recommended: every reviewer tripped on it.
- **The headline leaves out `modelling`'s goals** and shows them beside it in grey (R2). Recommended; the alternative is to keep one figure and make modelling hold.
- **The Loops page after R1.** Its rows will be on the boxes. Keep it as the sortable list of every goal, or remove it. Decide once R1 is in use, not before.

### Order of work

Quick fixes first, in any order; they are independent. Then R2 and R3 (mostly made of quick fixes), R1, R6 and R7 (they share the goal row and the evidence), then R4 and R5 (layout work, the largest), R8 alongside them, then R9, R10, R11's rename and R12.
