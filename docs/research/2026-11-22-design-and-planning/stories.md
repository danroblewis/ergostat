# ergostat: the user stories the design must make possible and obvious

Written by the design lead from the team's sixteen reviews (eight blind, eight briefed) and the owner's intent.
These are the stories the design team owns from now on. A story is met only when a newcomer can do it unaided.

## How to test a story

- The tester is someone who has not read the docs, the README or the YAML. They use only the running demo.
- Each story takes under ten minutes. Start at the demo URL given, at 1440x900 in light mode unless the story says otherwise.
- "Done when" is what the tester must be able to see or do. If they need a hint, the docs or the command line, the story fails.
- The stories say what must be possible, not how. Every fix must stay within the owner's decisions: no new pages or panels, two perspectives each true to its discipline, recognised diagram types only, items are not tickets, systems are namespaced, large systems matter, read-only for people except the gated actions.

## The demos

| Demo | URL | What it models |
|---|---|---|
| ticket-factory | http://127.0.0.1:8791 | Jira issues taken to merged pull requests, with gated outward actions |
| the-job | http://127.0.0.1:8792 | One engineer's job as goals, with asks of a person |
| image-squeeze | http://127.0.0.1:8793 | An image service and a lab of agents that optimises it |
| roadmap | http://127.0.0.1:8794 | Epics and tickets that wait on one another |
| software-factory | http://127.0.0.1:8796 | A factory of agents and the product it builds, with customers |
| big | http://127.0.0.1:8797 | Six systems, 24 loops: the layout at scale |

## The audiences

- **Newcomer**: opens a link a colleague sent, knows neither system dynamics nor control theory.
- **Product manager**: wants what really exists, whether it is healthy and what to expect.
- **SRE**: works from alerts and runbooks; wants which loop is off, why, and what to do.
- **Engineer**: runs the system and its agents; wants what acted, on what, and whether to trust the numbers.
- **System dynamics expert**: reads Sterman-style stock-and-flow diagrams everywhere else.
- **Control expert**: reads block diagrams and transfer functions everywhere else.

---

## A. First contact: what is this?

### A1. Say what the system is and what ergostat does, from the first screen
- **As** a newcomer **I want** the first screen to tell me what this system is for and what ergostat does with it **so that** I know why I am looking at it.
- **Demo:** http://127.0.0.1:8792/
- **Done when:** within one minute, without opening the Guide or any panel, the tester writes one sentence on what the modelled system is (one engineer's job, kept as goals) and one on what ergostat does with it (models it as feedback loops with goals and shows which hold). Both sentences can be traced to words on the diagram or its system boxes, not to a count such as "28 feedback loops inside".

### A2. Meet the subject before ergostat's own upkeep
- **As** a newcomer **I want** the system I came to see to come first, and ergostat's model of its own upkeep (`modelling`) to be set apart **so that** I do not conclude the product is about itself or is broken.
- **Demo:** http://127.0.0.1:8796/
- **Done when:** the first system box read, the first entry that asks for attention and the headline "off" figure all concern the product or the factory. The tester can point to `modelling`, say it is about the model and not the system, and say how many of the "off" goals are its own.

### A3. Learn the vocabulary in ten minutes and see it on my own system
- **As** a newcomer **I want** to find the Guide without being told and finish it on my own system **so that** I can read the diagrams afterwards.
- **Demo:** http://127.0.0.1:8791/
- **Done when:** the tester reaches the Guide from the first screen in one obvious step (also at 390 px wide), every frame renders legibly in light and dark, the last frame shows this demo's system both ways, and afterwards the tester points to one stock, one flow, one goal and one control loop in the live diagram.

### A4. Know what I may do here, in words I can act on
- **As** a newcomer **I want** to know that I only read, except for approving or denying what agents ask **so that** I am not afraid to click and not sent somewhere I cannot go.
- **Demo:** http://127.0.0.1:8791/
- **Done when:** the tester says, unprompted, "I can look at everything and I can approve or deny requests; nothing else changes the system", and shows where the requests wait. On the Diagram, Loops, Agents and Items pages, no text tells the reader to run a command, edit a YAML line or read a SPEC section, and no panel shows a leftover "…" placeholder.

### A5. Never mistake empty or loading for broken
- **As** a newcomer **I want** a view with nothing to draw, or still loading, to say so **so that** I do not report the tool as broken.
- **Demo:** http://127.0.0.1:8797/diagram?view=process
- **Done when:** the Process view on big says on the canvas, in words, why there is nothing to draw. Open and Into on any system show that something is happening within one second. An unknown address (`/nonsense`) gives a page with the navigation and a way back.

---

## B. Is it healthy, and what should I expect?

### B1. See which system is unhealthy with everything folded away
- **As** a product manager **I want** the closed diagram to be the control panel: each system with its goals, their values, bounds, health and trend **so that** I know where to look without reading a side list.
- **Demo:** http://127.0.0.1:8793/
- **Done when:** with every system closed and without using the side panel, the tester names each goal that is off, its system, its value and its bound (for example quality against ≥ 0.93), and says whether it is getting better or worse. Their answer matches the Loops page.

### B2. One health figure I can quote
- **As** an SRE **I want** the headline count of goals off to be steady, to agree everywhere and to lead to the goals it counts **so that** I can say it in an incident channel.
- **Demo:** http://127.0.0.1:8791/
- **Done when:** over five reloads in one minute the headline changes only when a goal has really changed state, and it agrees with the project switcher, the attention list and the Loops page at the same moment. Clicking it shows exactly those goals. A goal that crosses its bound again and again reads as flapping, with a count of crossings, and its behaviour label does not flip between reloads.

### B3. Tell "not there yet, on track" from "falling behind"
- **As** a product manager **I want** a goal that is being approached on schedule to look different from one that is failing **so that** red means something.
- **Demo:** http://127.0.0.1:8796/ (the goal `users-growing`, in the first minutes after start)
- **Done when:** without opening a chart, the tester says correctly whether `users-growing` is on track or falling behind, and whether a queue goal with one item waiting is a problem. Both answers come from words on the page, not from colour alone.

### B4. Read what to expect
- **As** a product manager **I want** each goal to say where it is heading and how likely **so that** I can set expectations.
- **Demo:** http://127.0.0.1:8796/
- **Done when:** at most one click from where a goal is shown, the tester reads a plain sentence such as "reaches 180 in about 6 minutes" or "likely to keep holding for the next 4 minutes", states how far ahead it looks, and can repeat it to a colleague without the words "p≈" or "Monte Carlo".

### B5. Numbers that agree and say what they are
- **As** an engineer **I want** every figure to say what it is (now or averaged, over which window, in which unit) and to match its copies **so that** I can trust what I quote.
- **Demo:** http://127.0.0.1:8796/diagram?view=dynamics&system=product
- **Done when:** for `users`, `signups` and `churn` the tester finds one rate per flow, with its window, and the same figure on the diagram, in the panel's chart heading and in its table. Rates in one system share one time base. A system's loop count on its box equals the count in its panel. The window named in the header is not longer than the record without saying so. No value prints a bare unit "1".

### B6. Say what really exists
- **As** a product manager **I want** the top-level diagram to tell me what the system holds and how its parts affect each other **so that** I can describe what we run and what we sell.
- **Demo:** http://127.0.0.1:8796/
- **Done when:** from the top level alone the tester writes three sentences: what the product holds (users, live bugs, missing operations), what the factory does, and how each affects the other with the direction of each effect. The demo's README confirms all three.

---

## C. Why is a loop off, and what is being done about it?

### C1. From "off" to the evidence in one step
- **As** an SRE **I want** every mention of an off goal to lead to that goal's evidence **so that** "what is wrong" is followed at once by "show me".
- **Demo:** http://127.0.0.1:8791/
- **Done when:** clicking the name of an off goal, wherever it appears (the attention list, a system box, the Loops page), opens its evidence (the measured value against its bound, what acted, the gap, over time) and marks it in the diagram. No name that looks like a link does nothing.

### C2. A runbook from the model: who acts, what it waits on, is this unusual, what to do
- **As** an SRE **I want** the evidence for an off goal to answer my questions in operational order **so that** I know my next step.
- **Demo:** http://127.0.0.1:8792/loops (the goal `tickets-within-sla`, which a person serves)
- **Done when:** from the goal's evidence the tester states who or what acts on it, when it last acted and what that moved, whether it is waiting on a person (with a link to that ask), how long it has been off against how long it usually takes to recover, and one suggested remedy with its reason in numbers. No answer is "no one process" or "not worked out" without saying what that means for them.

### C3. Evidence that does not contradict itself
- **As** an engineer **I want** what the evidence says about the actor to agree with the Record and the Agents page **so that** I can tell a dead actuator from one too small.
- **Demo:** http://127.0.0.1:8791/loops (the goal `requests-handled`)
- **Done when:** the tester compares the goal's evidence, the fixer's row on Agents and the Record for the same window and finds no disagreement about whether it was commanded, whether it ran and what it moved. Where it was commanded and moved nothing, one line says so. A goal's panel never says "nothing acts on its gap" while another surface names its actor.

### C4. See what is working on it right now
- **As** an engineer **I want** to see which agent is working on an off goal, on which items, and when it should hold again **so that** I know whether to wait or step in.
- **Demo:** http://127.0.0.1:8791/
- **Done when:** for a factory goal that is off, the tester names the agent acting on it, the item or items it holds at that moment and the expected time back, and reaches both the agent and the items by links from the goal's evidence.

### C5. Follow the chain of events
- **As** an SRE **I want** to go from a goal to the events behind it, in order, with real timestamps **so that** I can write the incident timeline.
- **Demo:** http://127.0.0.1:8797/loops
- **Done when:** from a goal's evidence, one click shows the Record narrowed to that goal and window, and the tester reads the sequence off, commanded, moved, holding. Timestamps carry the date and time zone, in the same format as on item pages. A filter that matches nothing says "nothing matches" with a way to clear it. Runs of identical unchanged events are folded.

### C6. Know which parts of the model to trust
- **As** an engineer **I want** doubt about the model drawn on the part it concerns **so that** I do not act on a diagnosis built on a bad fit.
- **Demo:** http://127.0.0.1:8791/diagram?view=dynamics&system=factory
- **Done when:** without visiting Check or Model, the tester points to the stocks whose change the known flows do not explain (with the amount, unit and window), the flows whose equation fits worse than its mean, and the processes not yet identified. Each is marked on the part itself, in the same way in every demo.

---

## D. What did an agent do, and what did it cost?

### D1. Who acts in this system
- **As** an engineer **I want** to see the people, AI agents, programs and rules that act, and what each is for **so that** I know what I am running.
- **Demo:** http://127.0.0.1:8791/agents
- **Done when:** the tester says how many of each kind there are and the figures match the rows listed under each heading. For any agent, the tester names the goal or goals it serves and how it is engaged (continuous, scheduled, on demand).

### D2. What one agent did
- **As** an engineer **I want** an agent's recent runs: when, on which item, the outcome, what it moved and what it asked to do outside **so that** I can review its work.
- **Demo:** http://127.0.0.1:8791/agents
- **Done when:** for the agent that works tickets, the tester lists its last three runs with time, item, outcome and any outward action asked, and follows one run to its item. Nothing on the agent contradicts itself (for example "not run by ergostat" beside "28 runs").

### D3. What it cost
- **As** a product manager **I want** the cost of each agent and of each item, and the total for the window **so that** I can weigh it against what it produced.
- **Demo:** http://127.0.0.1:8793/agents
- **Done when:** the tester states the cost of one agent, of one item and of the whole window, with the unit (money, tokens or machine time). Where the demo runs free stand-ins, the page says so in words; no cost shows as a bare dash or as $0.0000 without a reason.

### D4. Spot an agent that failed or never ran
- **As** an SRE **I want** a missed schedule or a failed run to stand out **so that** silent failures are not silent.
- **Demo:** http://127.0.0.1:8797/agents
- **Done when:** within one minute the tester finds every agent that is scheduled and has never run, has missed its schedule or last failed, and says why for one of them. These are marked as exceptions, not printed in the same grey as the rest.

---

## E. Approving what agents ask (the Inbox)

### E1. Find what waits for me
- **As** a newcomer **I want** the requests that wait for me to be apart from alarms and from the model's housekeeping, with a count **so that** I know what only I can move.
- **Demo:** http://127.0.0.1:8791/
- **Done when:** from any page the tester reaches the waiting requests in one step and says how many wait. Alarms, requests of a person and model housekeeping are visibly separate groups. At 390 px wide the waiting requests are reachable from the first screen.

### E2. Understand a request before answering it
- **As** an engineer **I want** each request to say in plain words what will happen, to what, who asks and why **so that** I never approve something I cannot read.
- **Demo:** http://127.0.0.1:8791/ and http://127.0.0.1:8792/
- **Done when:** for three waiting requests the tester says, before pressing anything, what approving will do (for example "move SCRUM-2 to Done in Jira"), which item it concerns and which agent asked. The exact command is available but is not the first line. For a request of a person (the-job), the tester says what they are asked to do and what any number they type means, with its unit. Where only Deny is offered, the request says why.

### E3. Approve or deny safely, and see that it happened
- **As** an SRE **I want** the request I act on to stay still, to confirm what was done and to show up in the item's history **so that** a production change is never a mis-click.
- **Demo:** http://127.0.0.1:8791/
- **Done when:** the list does not reorder while the pointer or keyboard focus is in it; the tester approves one request and denies another with a reason, using a label they can read in full; the page then says what was done and by whom; and the tester follows the request to its item and sees the action performed or refused. The whole story works by keyboard alone.

### E4. Many requests alike
- **As** an engineer **I want** identical requests folded into one **so that** two real asks are not buried under twenty-four of one kind.
- **Demo:** http://127.0.0.1:8797/
- **Done when:** the requests about missing units on big appear as one entry with its count, can be opened to see the members and can be answered together. Everything else that needs attention is visible without scrolling.

### E5. How much I have delegated
- **As** an engineer **I want** to see, per class of action, how often it was asked, approved and denied **so that** I can judge whether it still needs me.
- **Demo:** http://127.0.0.1:8791/
- **Done when:** the tester states, for one class of action (for example Jira transitions), how many were asked, approved and denied this week, whether it is currently held for approval or let through, and where they read that.

---

## F. Finding and following an item

### F1. Find an item by its name
- **As** an engineer **I want** to type an id or a few words of a title and land on the item **so that** I do not scroll for it.
- **Demo:** http://127.0.0.1:8791/items
- **Done when:** typing `SCRUM-2` narrows everything on the page to that item within the first screenful, and one click opens it. Typing nonsense shows "nothing matches" beside the search box, not below the fold. No column is cut off at 1440 px.

### F2. Where is it now, and what happened to it
- **As** a product manager **I want** an item's present state and its history in words **so that** I can answer "where is my ticket?".
- **Demo:** http://127.0.0.1:8791/items (then any ticket)
- **Done when:** the tester says the item's state, who or what holds it and for how long, the states it passed through with their times, what it cost, and any outward action taken for it. States it can no longer reach are not drawn as next steps. Its latest change reads as words ("waiting for review, 3 min"), not as an event name. Times use one format with the time zone.

### F3. Where items pile up
- **As** a product manager **I want** to see in which state work is waiting **so that** I know where the bottleneck is.
- **Demo:** http://127.0.0.1:8796/items
- **Done when:** the tester names the state holding the most tickets now and the step with the most rework, from the chart of states or the process map, and can match every band or node to its state by its label, in light and in dark, without relying on shades of grey.

### F4. From a stock to its items and back
- **As** an engineer **I want** to go from a number on the diagram to the items it counts, and from an item to where it sits in the model **so that** the model and the work are one thing.
- **Demo:** http://127.0.0.1:8791/diagram?view=dynamics&system=factory
- **Done when:** the tester clicks a stock with a value above zero, reaches the list of exactly those items (the count matches), opens one, and from it returns to the diagram with that stock marked.

### F5. What waits on what, and when it will be done
- **As** a product manager **I want** the dependencies between items and a finish estimate **so that** I can plan.
- **Demo:** http://127.0.0.1:8794/items
- **Done when:** on roadmap the tester names the critical path, one ticket that is blocked and what blocks it, and the expected finish of the last epic with its range. On a demo whose items have no relations (ticket-factory), the same view shows each item's states over time or says in plain words why there is nothing more to show, with no instruction to edit configuration.

### F6. Items are not only tickets
- **As** a newcomer **I want** to see what kinds of item this system keeps, and which ones finish and which live on **so that** I do not read the page as a ticket tracker.
- **Demo:** http://127.0.0.1:8793/items
- **Done when:** the tester lists the kinds of item in the demo with a one-line meaning for each (taken from the page), says for each whether its items complete or stay, and opens one that is not a unit of work (a case, a request or a session).

---

## G. Two perspectives, each true to its discipline

### G1. Know there are two perspectives and what each is for
- **As** a newcomer **I want** the place where I choose a view to say what each shows **so that** I understand "one model, read two ways".
- **Demo:** http://127.0.0.1:8796/
- **Done when:** within two minutes, without the Guide, the tester says that Dynamics shows what is (stocks, flows, feedback loops) and Blocks shows what is controlled (goals, controllers, processes), and that both draw the same model. The tester can also say the difference between a feedback loop (R or B) and a controlled goal, and the counts of each agree between a system and its parts.

### G2. Find the same part in both perspectives
- **As** an engineer **I want** a part I select in one view to be selected in the other **so that** I can compare the two readings.
- **Demo:** http://127.0.0.1:8793/diagram?view=dynamics&system=service
- **Done when:** the tester selects a stock, a flow and a goal in Dynamics and, for each, finds its counterpart in Blocks (the process output, the actuating signal, the reference and summing junction) still selected, either side by side or after switching. The side panel describes the same fact with the same substance in both, in each discipline's words.

### G3. A system dynamics expert reads Dynamics on sight
- **As** a system dynamics expert **I want** a stock-and-flow diagram like the ones I read everywhere else **so that** I trust it at once.
- **Demo:** http://127.0.0.1:8796/diagram?view=dynamics&system=product
- **Done when:** a tester who knows Sterman's notation confirms: only stocks, flows with valves and clouds, auxiliaries and signed connectors are drawn, with no sensor or controller boxes; every goal of the system appears as a goal-seeking structure (desired value, gap), including a goal nothing acts on; each R or B marker sits inside the loop it names; no label or marker covers another or a pipe; and no loop is called R or B while one of its links has no sign.

### G4. Find the loops that matter
- **As** a system dynamics expert **I want** a handful of named loops, with the minor ones folded **so that** the diagram tells the system's story.
- **Demo:** http://127.0.0.1:8796/diagram?view=dynamics&system=product
- **Done when:** the tester names the three to five loops that drive the product (growth, churn, quality) from the diagram, traces each by clicking its marker, and says which one dominates now. Loop names read as mechanisms, not as paths ("all-live via regressions and churn"), and no marker carries an unexplained "+1".

### G5. A control expert reads Blocks on sight
- **As** a control expert **I want** a block diagram like a textbook's **so that** I can check the regulation without translation.
- **Demo:** http://127.0.0.1:8791/diagram?view=blocks&system=making
- **Done when:** a tester who reads block diagrams confirms: each loop reads left to right on its own row (reference, summing junction, controller, process, output, sensor on the return); every block carries its function or says its law is not stated, with the agent's name as a caption; clicking a block gives its definition; sensors polled alike are drawn alike; a one-sided limit is not called a setpoint; drawn text is at least 11 px at the default view and nothing overlaps.

### G6. The top of Blocks shows control, and symbols keep their meaning
- **As** a control expert **I want** the top level to show what is regulated by what **so that** the hierarchy reads as a cascade, not a list of boxes.
- **Demo:** http://127.0.0.1:8796/diagram?view=blocks
- **Done when:** at the top level the tester identifies the references, the controlling subsystem (the factory), the controlled subsystem (the product), the signals between them and the feedback path, and says which goals are off, without colour. Every symbol used is defined in the legend. Opening a subsystem keeps its letter and its dimensions.

### G7. Judge one loop as an engineer would
- **As** a control expert **I want** a loop's controller law, process model and performance in a table I can scan **so that** I can say whether it is well regulated.
- **Demo:** http://127.0.0.1:8793/diagram?view=blocks&system=service
- **Done when:** for the tuner's loop the tester reads the controller law, the process model with its uncertainty (or "not identified", with what would identify it), the fit on held-out data with the measure defined, and time off, settling and saturation, all before any paragraph of prose. The panel says nothing about another loop.

### G8. Take the model into a design document
- **As** an engineer **I want** to export a diagram and what lies behind it **so that** I can explain the system in a proposal.
- **Demo:** http://127.0.0.1:8796/diagram?view=dynamics&system=product
- **Done when:** from the Export menu the tester gets a picture that is legible at document width in light mode, with its title and legend, and gets the model behind it (each variable's equation, unit and source for Dynamics; each loop's functions and signals for Blocks) in a form that can be read outside ergostat.

---

## H. Large systems, small screens, every reader

### H1. Read a large system from the top
- **As** an SRE **I want** the top level of a large system to show its shape and where the trouble is **so that** scale does not hide the answer.
- **Demo:** http://127.0.0.1:8797/
- **Done when:** within one minute the tester says how many systems there are, that each is a chain of four queues, and which system holds a goal that is off, in both Dynamics and Blocks. The systems are not seven identical boxes: each shows its own state. No text is below 11 px at the default view.

### H2. Open a system and land on it
- **As** an engineer **I want** opening a system to frame what I opened, readably, and to let me get back **so that** every step down does not need a manual zoom.
- **Demo:** http://127.0.0.1:8797/ (Open and Into on `api`) and http://127.0.0.1:8792/
- **Done when:** after Open or Into, the opened system is wholly in view with legible text, or the page says which way more lies; Fit includes every wire; "Open all" on big stays legible or offers the next step instead of shrinking; the breadcrumb returns to where the tester was. On the-job, whose top level is one wrapper, the tester reaches the stock-and-flow diagram of `incidents` in at most two clicks. A chain of queues reads in order, upstream first.

### H3. Every name says which system it belongs to
- **As** an SRE **I want** parts named in lists to carry their system **so that** I can find them among hundreds.
- **Demo:** http://127.0.0.1:8797/loops
- **Done when:** for any goal, stock or request named in the attention list, on Loops or in a suggestion, the tester says which system it belongs to from the name or its grouping alone, and finds its box on the diagram in one click. Inside a system's own view, the short name is used.

### H4. On call, on a phone
- **As** an SRE **I want** the phone to show what is off, by how much, and what waits for me **so that** I can decide whether to get up.
- **Demo:** http://127.0.0.1:8791/ at 390x844, light and dark
- **Done when:** on the first screen the tester reads each off goal with its value against its bound and how long it has been off, with no number cut off and no sideways scrolling; reaches every page, including the Guide, from the navigation; and reaches the waiting requests.

### H5. By keyboard, by screen reader, zoomed, and without relying on colour
- **As** a reader who does not use a mouse or does not see colour well **I want** the same three tasks to work for me **so that** the product is usable by everyone on the team.
- **Demo:** http://127.0.0.1:8791/
- **Done when:** using only the keyboard, the tester opens a system on the diagram, selects a stock and reads its panel, opens the evidence for an off goal from Loops, and answers a request, with focus always visible and returned sensibly. The current page and view are announced. "Off" is always carried by a word or a mark as well as colour. Text meets 4.5:1 contrast in light and dark. At 200% zoom every page is still reachable.

### H6. Send a colleague exactly what I see
- **As** an SRE **I want** the address to hold what I am looking at **so that** I can paste it into an incident channel or a design review.
- **Demo:** http://127.0.0.1:8797/loops
- **Done when:** the tester selects a goal, a time window and a view (and on Record, a filter), copies the address into a new tab, and sees the same goal, window and view. The headline count of goals off is itself a link to those goals.
