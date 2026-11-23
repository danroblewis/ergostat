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

## 2. The redesigns

Each is larger than a fix and is split into ordered pieces. Pieces marked (quick fix) are in section 3 and can be built first, on their own.

### R1. The closed system box is the control panel

**The problem.** Decision 1 says the control panel is the diagram with everything folded away, and SPEC §4 and the image-squeeze README promise that each closed box shows its measures with value, setpoint, health and trend. What is drawn is a name, 'N feedback loops inside' and, at best, port names with bare numbers. On the-job the first screen is two empty boxes; on big, seven identical ones while goals are off. In Blocks a closed system is 'Q_service 3×3' and nothing else. So health is read from a side list and a separate Loops page, which is the 'more panels' pattern the owner wants gone. Story B1 failed outright (possible: no), as did H1; all eight designers raised it, and after briefing each said it was worse than they first thought.

**The proposal.** Each closed system box carries, in this order: its name and description; one row per goal it holds (the goal's measure, its value, its bound, a trend over the header's window, a status word, and where it is heading); then its other exposed stocks and flows as today. Off goals come first; a box with an off goal has a heavier outline and 'N off' in its title row. The rows are the box's exposed parts, so nothing new is added to the page; a click on a row opens the evidence that exists. In Dynamics the row is the goal-seeking structure in miniature (level, desired level, gap). In Blocks the same block keeps its symbol and prints r and y on its ports with the status in text under it ('3 control loops, 1 off'), monochrome. At phone width the boxes stack one per row and become the home view, so '/' no longer needs to redirect to Loops. Once this lands, decide whether the Loops page still earns its place (its columns are now on the boxes); until then it stays.

**What it looks like.**

Dynamics, closed:

```
┌ product · textkit and its customers ──────────── 1 off ┐
│ off      missing-ops    2    ≤ 1     ▁▂▃▅   getting worse    │
│ holding  users        216    ≥ 180   ▂▃▅▆   240 in about 15m │
│ holding  bugs-live      0    ≤ 0     ▁▃▁▁   off 20% of 33m   │
│ ─ also ─  ◀ fixes  ◀ shipped  ◀ regressions   signups 13.2/min │
└──────────────────────────────────────── Open   Into ┘
```

Blocks, closed (monochrome, status in words):

```
r ≥ 180 ──▶┌───────────┐──▶ y_users = 216
r ≤ 0   ──▶│ P_product │──▶ y_bugs-live = 0
r ≤ 1   ──▶│   3×2     │──▶ y_missing-ops = 2   off
           └───────────┘
           3 control loops, 1 off
```

**Stories it serves.** B1, A1, B3, B4, B6, C1, H1, H4, G6

**Evidence.** story-1-b1-home.png, story-1-b1-blocks.png, story-0-a1-home.png, story-4-big-home.png, story-7-h1-home.png, story-7-h1-blocks.png, sreb-is-closed.png, infodb-is-home.png, pmb-img-blocks-closed.png, pmb-sf-users-panel.png (the module panel's 'Its measures, on one time axis' already holds the data), newcomer-briefed-tf-loops.png (the Loops columns are the rows)

**Pieces, in order.**

1. Description in the box and the caption above the diagram (quick fixes 'Each closed system box says what the system is', 'A caption names the diagram…').
2. 'N off' and the heavier outline on a box that holds an off goal, both views (quick fix 'A system box that holds an off goal says so…').
3. Goal rows in the Dynamics box: status word, measure, value, bound; off first; a row click opens the evidence and rings the part. Acceptance is story B1 on image-squeeze without the side list.
4. Trend on each row: a sparkline on the header's window with the bound as a dashed line, and a word ('getting worse', 'recovering', 'steady').
5. Blocks: r and y with values on the closed block's ports, and the status line under the block.
6. 'Where it is heading' in the last cell of each row (needs R6's sentence).
7. A closed system also shows the total of the items counted inside it, so a stock above zero is visible from outside (story F4).
8. Phone: the stacked boxes are the home view at 390 px; remove the redirect to Loops.
9. Review the Loops page: either remove it (its rows are on the boxes) or keep it as the sortable list of every goal. Owner's call after the pieces above are in use.

### R2. The system comes first; ergostat's own upkeep is set apart

**The problem.** Every demo models ergostat's upkeep of its own model as a system, 'modelling'. That is intended. But it is drawn first (top left), its two goals lead the attention list in all six demos, they are permanently off (requests-handled 94 to 100% of the time), and on the-job and software-factory they are the whole of the red '2 loops off'. On big, 24 of 26 attention entries are its requests. It also stops the-job's only system from opening. All sixteen reviews name this; the newcomer's conclusion was 'the tool is broken, or is about itself'. Its names carry no system, against decision 5.

**The proposal.** Keep modelling as a system, and treat it everywhere as the model's upkeep, not the subject: drawn last and dashed with a one-line label; counted apart in the header ('0 goals off · model upkeep 2'); listed after the system's own goals, under its own rule, with its requests folded; ignored by the 'alone at its level starts open' rule; collapsed at the foot of Loops. Names in every list carry their system. Then make it hold in the demos: a fixer that runs every minute and moves nothing is a dead actuator, and the first lesson every demo teaches should not be that ergostat's own feedback fails.

**What it looks like.**

Top level of software-factory: product and factory fill the canvas with their signed links; bottom right, a smaller dashed box 'modelling · ergostat's upkeep of this model, not the system · 2 off'. Header: '0 goals off · model upkeep 2'. Side list: 'Goals off 0', then under a thin rule 'Model upkeep: 2 off · 24 requests alike'.

**Stories it serves.** A2, A1, B2, H1, H3, E4

**Evidence.** story-0-a2-home.png, story-0-a2-modelling-into.png, story-0-a2-loops.png, pm-big-home.png, pmb-job-loops.png, ixdb-sf-home.png, sreb-big-home.png, ceb-annotated-sf-top.png, story-7-h3-loops.png

**Pieces, in order.**

1. Layout: modelling last, dashed, labelled (quick fix).
2. Header and switcher count it apart (quick fix).
3. A system alone at its level opens (quick fix).
4. System names on every list name; Loops grouped by system with modelling collapsed (quick fix).
5. Side list: the system's goals first, modelling's under their own rule (with R3's grouping).
6. Unexplained-stock notes and units requests go to model housekeeping, never to the goals group.
7. Demo and template work, outside the page: make requests-handled and model-fits hold in a healthy demo (the fixer answers what it can; what it cannot is one folded request, not a goal off for ever). A missing unit is a Check finding drawn as 'unit ?' on the stock, not 24 requests of the owner.

### R3. Needs attention becomes the Inbox

**The problem.** Decision 7 makes approving or denying the one thing people do, in 'the Inbox'. There is no Inbox. Requests are rows in a side list on one page, mixed with alarms and model notes, capped at about six rows, re-sorted every few seconds, and absent from the first screen on a phone. Rows are machine text cut off with '…', point to a command line, have inputs truncated to 'how ma' and 'why (to de', put Deny before its reason in tab order, and never confirm what was done. A typed reason was lost when its row vanished. On big 24 identical requests fill the list. Story E3 and E4 failed; E1, E2 and E5 were at best partly possible.

**The proposal.** Keep the side list where it is and make it the Inbox, in three fixed groups: Waiting for you, Goals off, Model housekeeping. A request is one sentence in plain words (what will happen, to what, who asks, why), with the command behind a disclosure, a labelled reason, and Approve and Deny of equal weight named for what they answer. The list holds still while the pointer or focus is in it; an answered row says what was done and by whom and links to the item, whose history shows it. Requests alike fold into one row with a count and one answer. A 'N wait for you' link in the header reaches the group from every page and is first on a phone. No new page: the count in the header, the group in the side list and the item pages carry all of it.

**What it looks like.**

```
Waiting for you 2
  Move SCRUM-7 to Done in Jira
  for ticket/SCRUM-7 · asked by close · waiting 12m
  ▸ the exact command
  Reason for denying [______________________]
  [ Approve the move ]  [ Deny the move ]
  jira-transition: 24 asked, 24 approved, 0 denied this week · held for approval
```

```
  You are asked: decide the flag ramp 'checkout-v2' (it has waited a working day)
  Ramps you decided (number) [__]   [ Done ]
```

```
Goals off 1
  off · product · missing-ops 2, wanted ≤ 1 · off for 4m, usually back in 30s
```

```
▸ Model housekeeping 26
  24 stocks have no unit (api … web) · Deny all
  2 stocks changed more than their flows explain
```

**Stories it serves.** E1, E2, E3, E4, E5, A4, H4, H5

**Evidence.** story-4-home.png, story-4-job-home.png, story-4-big-home.png, story-4-still-8792.png, story-4-typed-lost.png, story-4-kbd-deny-focus.png, story-4-phone-job.png, story-4-action-dark.png, story-4-actions-all.png, ixdb-tf-approve-item.png, sre-tf-attn-click.png, a11yb-8792-root.png

**Pieces, in order.**

1. Three headed groups in a fixed order, with counts (quick fix).
2. The request sentence, full person asks, command in a disclosure (quick fix); labels and units on inputs (quick fix); identifiers safe from the rewrite (quick fix).
3. Stillness: no reorder or removal while the pointer or focus is inside; pending updates counted at the top (quick fix).
4. Controls: reason before Deny, named buttons of equal weight (quick fix).
5. Confirmation in place, and the answer in the item's history with who answered (quick fix).
6. Fold requests alike, with 'answer all' (quick fix).
7. Header link 'N wait for you' on every page, first on a phone, announced politely (quick fixes).
8. Per-class tally on the Actions table, and the same line under each request of that class (quick fix).
9. A sentence at the head of the group that says what a person may do here: 'You can look at everything. Approving or denying these is the only thing that changes the system.' (story A4).
10. Demo: ticket-factory should leave a few outward actions waiting (its stand-in approved all 121), so the Inbox can be seen working.

### R4. Blocks reads as a textbook block diagram at every level

**The problem.** At the leaf the notation is right: summing junctions, r/e/u/y/d, H on the return, relay and dead-band glyphs, C(z) with sampler and hold. Above the leaf it is not a block diagram. The top level is opaque 'Q' boxes: seven in a column with no signals on big, two unconnected on the-job, one unlabelled wire on ticket-factory; no reference, no summing junction, nothing marked off. Q is undefined and reads to a control engineer as the Youla parameter; it changes to P with different dimensions when opened. Inside, many blocks hold an agent's name and no function; loops are interleaved rather than one per row; a chain runs bottom-up; a ceiling is drawn as 'r = 0'; text is 7 to 9 px and Fit goes to 4 px. Stories G5 and G6 were only partly possible.

**The proposal.** Draw the hierarchy with the same grammar as the leaf. At the top level each system is classified by what it holds: a controller subsystem (C), a plant-only subsystem (P, the same letter and dimensions when opened), or a named subsystem block when mixed. References enter through a summing junction; signals between systems are labelled (u_deployed); the fed-back output returns through H. Systems that share no signal are drawn as parallel rows, each with its own r and y, under the note 'no signals between these'. Inside, one loop per row, left to right, upstream first, with couplings between rows drawn downwards; every block carries its function with the agent as a caption; a one-sided limit is a limit; sensors polled alike look alike; crossings hop and only real take-offs get a dot. Status is carried without colour: an off loop's e is printed bold with its value and the word 'off'. Text never goes below 11 px: when the rows do not fit, show the rows that do and say which way the rest lies.

**What it looks like.**

Top level, software-factory:

```
r = [bugs ≤ 0, missing ≤ 1, users ≥ 180] ─/3─▶(Σ)── e ──▶[ C_factory 1×3 ]── u_deployed ──▶[ P_product(s) 3×2 ]──┬─/3─▶ y_product
                                              ▲ −                                           ▲ d (customers)   │
                                              └──────────────────────[ H ]────────────────────────────────────┘
───────────────────────────────────────────────────────────────────────────────────────────────
model upkeep:   r ──▶(Σ)──▶[ C_modelling ]──▶[ P_model ]──▶ y      2 control loops, 2 off
```

Top level, big: six rows, one per system, each 'r_api ─▶(Σ)─▶[ api: 4 loops in series ]─▶ y_api', the off one marked 'off: 1 of 4'; caption 'no signals between these systems'.

Inside api: q0's loop on row 1, q1's on row 2 one step to the right, with u_q0,out running down into the + of q1's junction.

**Stories it serves.** G5, G6, H1, H2, G7

**Evidence.** story-7-h1-blocks.png, story-6-g6-blocks-top.png, ceb-annotated-sf-top.png, ceb-big-blocks-dark.png, sreb-job-blocks-fit.png, story-6-g5-blocks-making.png, ceb-big-api-blocks.png, story-7-h2-into-api-blocks.png, ceb-tf-modelling-blocks-fit.png, ceb-is-service-fit.png, ce-sf-blocks-factory.png, ce-sf-blocks-product.png

**Pieces, in order.**

1. Legend and naming: define the symbol and p×m, one typeface, name once (quick fix).
2. A function in every block, agent as caption (quick fix); limits as limits (quick fix); sensors alike (quick fix).
3. Classify subsystems: C, P or a named block; the same letter and dimensions at both levels (count the disturbance at both). Drop Q.
4. Top level: references and summing junction ahead of the controlling subsystem, labelled signals between systems, H on the return. Acceptance is story G6 on software-factory.
5. Uncoupled systems as parallel rows with their own r and y, and the 'no signals between these' caption (big, the-job).
6. Row layout inside a system: one loop per row in signal order, upstream first, couplings downward; the sensor under its own process. Acceptance is story G5 on ticket-factory making and the chain on big api.
7. Status without colour: bold e with its value and 'off' on an off loop; the off count under a closed block (with R1).
8. Minimum 11 px: scale the drawing, not the text; when rows do not fit, show those that do with 'more below' (with R8).
9. Crossings: hop at a crossing, dot only at a take-off, vector slash away from crossings.
10. Model health on the blocks: 'balance off by 30.5' or 'not identified' under P, 'commanded 18×, moved 0' under an actuator, from the same source as the evidence panel.

### R5. Dynamics tells the system's story: goals drawn, a handful of named loops, doubt on the part

**The problem.** The leaf notation is Sterman's and should stay. But on software-factory's product, the demo's subject, none of its three goals is drawn (image-squeeze and big do draw 'desired' and 'gap'); all 18 elementary loops are drawn with path names ('all-live via regressions and churn and asks'), their markers and names piled on each other and on the users stock; loops are called R or B while most of their links show no sign; '+1' on a marker is unexplained; polarity signs at the top level cannot be matched to their links; nothing on any part says where the model is doubtful, though the page already holds hidden rings for it. Stories G3, G4 and C6 failed.

**The proposal.** Four changes, all inside the stock-and-flow diagram. (1) Every goal is drawn as goal-seeking structure in the system that owns it: desired level, gap, signed links. When its controller is in another system the gap's link leaves through a port ('→ factory'); when nothing serves it the gap has no outgoing link and a small 'no feedback' mark, which is the finding drawn the SD way. (2) Draw the loops that matter: those the model names, plus the shortest loop through each goal's gap; fold the rest into the side list ('13 minor loops'). A loop may carry a mechanism name in the model ('quality erosion'), written by whoever maintains the model through the Supervisor; its path stays in its panel. (3) A loop is R or B only when every link is signed; signs that hold by definition are filled in. (4) Markers sit inside the loop they name; markers, names and signs are obstacles in layout and never cover a part, a pipe or each other. Status and doubt are drawn on the part: an off goal's gap in the one accent colour with the word 'off'; a dashed stock with its unexplained change; a hatched valve on a flow whose equation fits worse than its mean; '?' on an unidentified process. At 'Everything' this gives the overview an SD study opens with: sectors, their goals, and the named loops between them.

**What it looks like.**

product, after:

```
desired users ≥ 180 ──(−)──▶ users gap ◀──(+)── [ users 225 ]══▶ churn 7.3 users/min (mean of 33m)
                                │ → factory: product-manager
     (R1) word of mouth        (B2) quality erosion        (B3) feature pull        … 13 minor loops in the list
[ bugs-live 0 ] dashed outline · '−1 op unexplained in 44m'        churn valve hatched · 'fits worse than its mean'
```

**Stories it serves.** G3, G4, C6, B6, B1, C1

**Evidence.** story-6-g3-dyn-product.png, story-6-g3-crop.png, story-6-g4-R2.png, story-6-g4-B1.png, story-1-dark-product.png, sdxb-annotated-product.png, sdxb-8796-product.png, sdxb-8797-api.png (goals drawn correctly on big), newcomer-briefed-is-service.png, story-2-c6-modelling.png, story-2-c6-factory-all-open.png, story-1-b6-zoom.png

**Pieces, in order.**

1. Signs: definitional signs filled, '?' in place of R or B otherwise, plain names (quick fix). Polarity signs on their own arrows (quick fix).
2. Doubt on stocks: show the existing ring with its amount, unit and window (quick fix).
3. Every goal drawn as desired level and gap in its own system, with the port link or the 'no feedback' mark. Acceptance: on software-factory product the three goals are drawn; the users panel and the diagram agree.
4. Loop folding: draw named loops and one per goal; the rest listed as minor, drawn when selected. Remove '+1'.
5. Mechanism names: a loop may be named in the model; the diagram shows the name, the panel the path. Name the product's loops in the software-factory demo.
6. Placement: markers at the centre of their loop's polygon; a collision pass for markers, names and signs against parts, pipes and each other; add it to the layout rules and the render tests.
7. Doubt on flows and processes: hatched valve with 'fits worse than its mean'; '?' where a process is not identified; one line each in 'How to read it'; the same marks in every demo.
8. Status on the part: the off goal's gap and its loop marker in the accent colour with 'off'; which loop dominates now named at the head of the loops list.
9. Short pipes: clouds beside their valve, one bend at most (the owner's layout rules 1, 4 and 5, enforced on big's q2 → q3).

### R6. 'Off' tells the truth: on track, falling behind, flapping, and what to expect

**The problem.** A goal approaching its bound on schedule (users climbing steadily to 180) is red and 'off 100%' exactly like a failing one; a queue goal goes red each time one item waits (29 times in 33 minutes); a goal that crossed its bound 23 times reads 'holding'. The headline moves between 2 and 6 within a minute on some demos. The forecast, the thing that makes this a dynamics tool, is two clicks down, takes about 20 s, looks 4 to 8 minutes ahead whatever the window, and reads 'off at +8m15s with p≈0.07 (100 runs)', which leads with 'off' for a goal 93% likely to hold. Stories B3 failed; B2 and B4 partly.

**The proposal.** Give a goal's state the words a person would use, and say where it is heading wherever the goal is shown. States: holding; approaching (not at its bound yet, closing at a rate that reaches it within the horizon) in neutral ink; off; flapping (with its crossing count). A queue goal says in words whether one waiting item is within its tolerance or grace time. The headline counts goals off for longer than their grace, with hysteresis, and agrees with the switcher, the side list and Loops at the same moment. The forecast becomes one sentence the right way round ('likely to keep holding for the next 8 minutes, about 9 in 10', 'reaches 180 in about 6 minutes', 'will stay off'), with the horizon stated and tied to the window, and the method behind a disclosure. It is computed with the page, not on demand, and shown in the Loops row and on the box row (R1).

**What it looks like.**

Loops row: 'users-growing · approaching · 173 of ≥ 180 · reaches 180 in about 6m'.  'backlog-clear · holding · 1 waiting, within its grace of 2m'.  'nothing-awaits-approval · flapping (23 crossings in 32m)'.  Window menu: 'Last 1h · ahead 15m'.

**Stories it serves.** B2, B3, B4, H4, C4

**Evidence.** story-1-b3-loops.png, story-1-b3-users-detail.png, story-1-b3-backlog-detail.png, story-1-b4-ahead-users-growing.png, story-1-b2-loop-detail.png, pm-sf-users-growing.png, pm-sf-users-ahead.png, pmb-sf-users-stock.png, sre-big-loop-osc.png, pm-job-loops-4s.png

**Pieces, in order.**

1. Hysteresis on behaviour labels, '<1%', and the 'flapping' word (quick fix).
2. The forecast sentence rewritten in words, with p and the run count in a title or disclosure.
3. The 'approaching' state from the projection and the suggestion engine's own verdict ('keeps up on average' against 'falling behind'), in neutral ink, on Loops, the side list and the box rows.
4. Grace and tolerance for queue goals stated in words on the row; the headline counts only goals off past their grace.
5. The forecast computed with the page load and cached per window, so it is present on first paint.
6. An 'expected' cell on each Loops row (replacing 'back in') and on each box row.
7. Horizon tied to the window, with 'ahead' added to the window menu that exists.
8. The headline agrees everywhere: one function feeds the header, the switcher, the side list's group and Loops.

### R7. The evidence for a goal is a runbook, and it agrees with the Record and Agents

**The problem.** The evidence panel is the best thing in the product (y with r, u and e on one time axis, crossings, decisions) and every reviewer said to keep it. But the route to it is broken (goal names that look like links do nothing; opening it marks nothing on the diagram), its statements about the actor contradict the Record and the Agents page on the same screen ('never opened' beside 'Moves 1.62/h' beside 34 runs), and it answers an SRE's questions in a modeller's order and words ('Not worked out: it has no one process'). It has no link to the person's waiting ask, the items held, or the events behind it. Stories C3, C4 and C5 failed; C1 and C2 partly.

**The proposal.** Keep the panel and its charts. Put four lines above them, built from the same counts the Record and Agents use: who or what acts and what it did ('fixer: commanded 34 times, ran 34, moved nothing; its log: no open request the rule tier answers'); what it waits on (a link to the person's ask, or the items it holds); how long it has been off against how long it usually takes; one suggested remedy with its numbers. Every mention of a goal anywhere opens this panel and rings the part. Every crossing links to the Record narrowed to this goal and time, with real timestamps and repeated events folded. The panel, the selection and the window live in the address.

**What it looks like.**

```
tickets-within-sla · off for 4m · usually back in 30s (slowest 41s): longer than usual
Acts: run-commands (a person) · asked 6m ago · nothing moved since
Waiting on: person/run-commands@2066 → answer it
Try: … because 3 tickets arrive per hour and 1 is answered
[ y with r ]  [ u ]  [ e ]                       Crossings → Record
```

**Stories it serves.** C1, C2, C3, C4, C5, H6, D2

**Evidence.** story-2-c1-evidence.png, story-2-c1-click-attention-name.png, story-2-c2-evidence-off.png, story-2-c3-fixer-link-retry.png, story-2-c3-agents.png, story-2-c3-record.png, story-2-c4-located-worked.png, story-2-c5-evidence.png, story-2-c5-record.png, sreb-job-loop-panel.png, ceb-tf-fixer-panel.png

**Pieces, in order.**

1. Goal names are links everywhere, and the part is ringed (quick fix).
2. One source for the actor: commanded, ran, moved, with the log's last line (quick fix).
3. 'Off for … · usually back in …' and the expected time back (quick fix).
4. Links to the waiting ask and to the items held (quick fix).
5. Crossings link to the Record narrowed to the goal; the filter matches item and source and lives in the address (quick fix); folded repeats (quick fix); one time format (quick fix).
6. Selection and window in the address (quick fix).
7. Reorder the panel: the four lines, the charts, then parts and prose; the remedy line taken from Suggestions for this goal, shown when it has a verdict.
8. A quiet system says so: when no goal of a system is off, its box and Loops group read 'all holding, nothing in flight'.

### R8. Opening, fitting and large systems: fold, never shrink or blank

**The problem.** Every step down needs a manual repair. Into blanks the canvas and the side list for seconds; Open drops the opened system half off-screen; Fit leaves wires outside and shrinks text to 4 to 8 px; 'More beyond the edge' does not say where; 'Open all' on big shows about one system; a chain of queues is drawn downstream-first in places; at phone width the diagram opens on an empty or cut canvas. Decision 6 says large systems matter, and the big and software-factory demos are where each of these fails first.

**The proposal.** One rule for every change of view: frame what the reader just asked for, at a text size they can read, and say where the rest is. After Open or Into the opened system is in view; Fit includes every node, wire and label; text never goes below 11 px (the diagram pans instead, with hints that name a direction and move there when clicked); the previous drawing stays, dimmed, until the next is ready. 'Open all' on a large model opens systems as their control-panel boxes (R1) rather than everything at once, and offers 'Into' for the off one. Chains are laid out upstream first in both views. At phone width the view opens fitted on the first off part.

**What it looks like.**

After Open on api (big): api's frame fills the canvas at 11 px or more; the other six stay as closed boxes around it, their order unchanged; bottom edge: 'more below ↓ (billing, build)'.

**Stories it serves.** H2, H1, A5, H4

**Evidence.** story-0-a5-into-300ms.png, story-0-a5-open-300ms.png, story-7-h2-open-api.png, story-7-h2-open-api-fit.png, story-7-h2-open-all.png, story-7-h2-into-api-blocks.png, story-7-h2-thejob-incidents.png, ixd-big-open-all-fit.png, ceb-is-service-open.png, ceb-is-service-fit.png, story-6-phone-dark-dyn-product.png

**Pieces, in order.**

1. Never blank: dimmed old drawing and 'Opening …' on the canvas (quick fix).
2. Frame what was opened; Fit includes every wire; hints name a direction (quick fix).
3. Phone: fitted on load (quick fix).
4. A floor of 11 px on drawn text in both views, with panning and direction hints instead of shrinking; add it to the render tests as a measured check on every demo and view.
5. Opening one system leaves the others where they were (no re-layout that moves closed boxes).
6. 'Open all' on a model that will not fit opens to the control-panel boxes and says 'Into' for the rest.
7. Chains upstream first, top-left, in Dynamics and Blocks (big api; the-job incidents).
8. Long connectors leaving an opened system are routed along its frame, not across the drawing.

### R9. The diagram can be read without a mouse or sight

**The problem.** The owner's decision is that the diagram is the interface. Today the diagram is one unnamed SVG that Tab skips: nothing in it can take focus, so a keyboard or screen-reader user cannot open a system, select a stock, or read a block's definition, and the Loops and Agents rows that would be the text twin are mouse-only too. View and page state are not announced. Story H5 failed. As long as this holds, those users need exactly the extra pages the owner wants to remove.

**The proposal.** Make the diagram itself the accessible structure, with no added view. First make every clickable part focusable with a name and Enter (quick fix). Then give each diagram one tab stop and let arrow keys follow the lines its discipline reads along: in Dynamics, Right and Left along the pipe, Up and Down along connectors (announcing polarity), L through the loops a part is in; in Blocks, Right and Left along the signal from r to y, Down into the feedback path. Each part announces what a sighted expert reads: 'Stock bytes-per-mp, 52.8 KB per MP, desired ≤ 20, 32.8 over, off. In loops B2 and B36.' The side panel's loop rows are the entry points. The MathML definitions already there are spoken as they are.

**What it looks like.**

Nothing new on screen except the focus ring moving along a pipe or a signal line.

**Stories it serves.** H5, E3

**Evidence.** story-7-h5-loops-kbd.png, a11y-8791-home.png, a11y-8797-stock-click.png, a11yb-8793-into-service-block-click.png, a11yb-8793-deadband-panel.png

**Pieces, in order.**

1. Focusable parts with names and Enter; focus into the panel and back (quick fix).
2. Loops and Agents rows as buttons (in quick fix 'Every goal name is a link…').
3. State announced: aria-current, aria-pressed, table and control names (quick fix); live counts (quick fix).
4. One tab stop per diagram with roving focus; arrow keys along pipes and connectors (Dynamics) and along signals (Blocks); I and Escape for Into and back.
5. Spoken names for every part kind in each discipline's words, including state and the loops or control loop it belongs to.
6. A keyboard run of story H5 added to the browser tests.

### R10. Take the model out: export what lies behind the picture

**The problem.** WHY.md leads with design documents, proposals and projection. Export offers SVG, Design SVG and PNG; the PNG is defective, and nothing exports the model. An SD modeller cannot audit the equations in one pass; a control engineer cannot take P(s), C(z) and the traces to another tool. Both experts called it the biggest missed chance for their audience. Story G8: picture yes, model no.

**The proposal.** All in the Export menu that exists, for the system drawn. Dynamics: 'Model (Markdown)' with each variable's equation, unit, source (declared, calibrated, measured) and note, and each loop with its polarity; then 'Model (XMILE)'. Blocks: 'Loops (Markdown)' with each loop's r, C, P with ±σ, H and sample period; then 'Loops (JSON)' and the window's r, y_m, u and e as CSV. The picture exports in light mode with title, window and legend.

**What it looks like.**

Export ▾  Picture (PNG) · Picture (SVG) · Design SVG · Model (Markdown) · Model (XMILE) | Loops (Markdown) · Loops (JSON) · Traces (CSV)

**Stories it serves.** G8

**Evidence.** story-6-g8-export-menu.png, story-6-g8-export-dynamics-*.png, story-6-g8-export-blocks-*.png, ce-tf-export.png, sdx-8796-export.png, sdx-8796-model.png

**Pieces, in order.**

1. Fix the PNG and add the legend to the Blocks picture (quick fix).
2. Dynamics: Model (Markdown), the variable table and loop list of the system drawn.
3. Blocks: Loops (Markdown), the loop table of the system drawn.
4. Dynamics: XMILE.
5. Blocks: Loops (JSON) and Traces (CSV).

### R11. One word for each thing: goal, feedback loop, control loop

**The problem.** 'Loop' names two objects: an R or B feedback loop (49 of them on ticket-factory) and a goal with its control path (16, with setpoints, 'off' and 'holding'). Both sit in one panel under the same word, the header says 'N loops off', and the counts cannot be reconciled. The same goal is 'desired = 0: excess 37', 'setpoint ≤ 0 (off by 36)' and 'error −36' on three surfaces, and the Dynamics wording is produced by a find-and-replace that corrupts identifiers. The per-view vocabulary is right and should stay; its edges are what fail. Story G1 was only partly possible.

**The proposal.** Use 'goal' for what is wanted and whether it holds: the header ('2 goals off'), the side list, the box rows and the page that lists them. Use 'feedback loop' only for R and B in Dynamics, and 'control loop' in Blocks. Where a feedback loop closes a goal, say so on both ('B40 serves goal model-fits'). Outside Blocks, say how far off in plain words with the bound as a bound ('37 over its limit of ≤ 0', '21 short of ≥ 30'); keep e = r − y with its sign in Blocks and the scope. This changes docs/vocabulary.md, where 'Loop (holding, off)' is listed on purpose, so it is the owner's decision; the recommendation is to make it, because every one of the eight reviewers tripped on it and the stories already speak of goals.

**What it looks like.**

Header: '2 goals off'. Nav: 'Goals' in place of 'Loops' (the same page). Dynamics side list: 'Feedback loops 18 · 5 R, 13 B'. Blocks side list: 'Control loops 8'.

**Stories it serves.** G1, B1, B5, H3

**Evidence.** story-6-g1-home.png, story-6-g6-click-factory.png, ceb-tf-home.png, ceb-tf-blocks.png, sdx-8791-loops.png, infod-tf-home.png, infod-tf-blocks.png, infod-tf-loops.png, ixdb-job-sd-open.png

**Pieces, in order.**

1. Dynamics side list says 'goal'; Blocks says 'control loop' (quick fix). Bounds written one way (quick fix). Identifiers safe (quick fix). Loop counts consistent (quick fix).
2. Header and switcher read 'N goals off'.
3. Owner's decision, then: rename the Loops page and nav entry to 'Goals'; update docs/vocabulary.md and the Guide's frames to match.
4. Cross-reference: each feedback loop that closes a goal names it; each goal's evidence names its feedback loops and its controller, each a link into its view.
5. One phrase for 'how far off' outside Blocks, from one function.

### R12. Fewer pages, and demos that show the claims

**The problem.** Two things stand behind the three doubts (is it useful, will people use it, will it matter) that no page change answers. First, eight top-level pages do not fit a phone or 200% zoom, and three of them (Loops, Agents, Model) are tables of the same goals again, while Check is a lint list for whoever maintains the model. Second, the demos do not show what WHY.md argues: no loop in six demos has an identified process, so margins, closed-loop step, Bode and tuning never appear; no demo has an observed external controller ('fixing the controls we already pay for'); every demo's own upkeep is off; ticket-factory leaves nothing to approve.

**The proposal.** Pages: fold Check into Model as its 'Findings' section (both answer 'is the model right?'), which leaves seven; revisit Loops after R1 and Agents after R4 (an agent is a block; its runs and cost fit that block's panel). Decide each by use, not now. Demos: one whose loop has an identified process with its step test already run; one with an observed external controller (the kube-sim autoscaler is the candidate) identified as C(s) with its saturation and lag and a proposed retune; a healthy start where modelling holds; a few outward actions left waiting.

**What it looks like.**

Nav: Diagram · Goals · Agents · Items · Record · Model · Guide.

**Stories it serves.** A2, A3, E2, G7, H4

**Evidence.** a11y-8792-zoom200-diagram.png, story-7-h4-phone-light.png, ceb-is-ctrl-panel.png ('Its process is not identified yet, so no margins…'), newcomer-briefed-tf-model.png, pm-tf-check.png, story-4-actions-all.png

**Pieces, in order.**

1. Check becomes a section of Model, as tables (with quick fix 'Check and the Model page say each thing once').
2. Demo: modelling holds at start; ticket-factory leaves actions waiting (with R2 and R3).
3. Demo: a loop with an identified process, so the controller panel shows its margins and tuning.
4. Demo: an observed external controller (kube-sim's autoscaler) identified and judged.
5. After R1 is in use: decide on Loops. After R4: decide on Agents.

## 3. The quick fixes

82 small changes, each buildable and testable alone. Duplicates across the sixteen reviews and eight story groups are merged; points of taste with no cost to a reader are dropped. Screenshot names are files in `shots/`.

### First contact

#### Q01. Each closed system box says what the system is

- **Pages:** /diagram (Dynamics, top level and any level with closed systems)
- **Problem:** A closed box says only 'N feedback loops inside'. The description each system already has shows only after a click, or as '…'. A newcomer cannot say what 'job' or 'product' is.
- **Change:** Under the box name print the system's description ('textkit and its customers'). Remove 'N feedback loops inside' from the box; keep the count in the system's panel.
- **Acceptance:** On :8792/ the box 'job' and on :8796/ the box 'product' each contain their description text; no SVG text on a closed box matches /feedback loops inside/.
- **Stories:** A1, B6
- **Evidence:** story-0-a1-home.png, story-1-b3-home.png, story-1-b6-click-*.png, newcomer-briefed-job-home.png, infodb-job-root.png, pmb-sf-users-panel.png

#### Q02. A caption names the diagram, the model's purpose and the verdict

- **Pages:** /diagram (all views)
- **Problem:** The home page has no h1, the SVG has no name, and nothing says which discipline's diagram this is or what the model is for. The model's purpose sentence is never shown.
- **Change:** One line under the view switch, which is the page's h1 and the SVG's accessible name: 'Stock-and-flow diagram (system dynamics) · the-job: <purpose> · 2 systems · 28 goals, 2 off' and 'Block diagram (control) · … · 16 control loops, 2 off'.
- **Acceptance:** /diagram has exactly one h1; it contains the project's purpose text and the view's diagram type; the diagram svg has aria-labelledby pointing at it; switching to Blocks changes the type words.
- **Stories:** A1, G1, H5
- **Evidence:** a11yb-8791-dynamics-light.png, a11yb-8791-blocks-light.png, infodb-job-root.png, sdxb-8796-home.png

#### Q03. The view switch says what each view shows

- **Pages:** /diagram toolbar
- **Problem:** 'Dynamics | Blocks | Process' explain themselves only in hover titles, which a phone never shows. 'One model, read two ways' is on Guide frame 2 only.
- **Change:** Visible labels: 'Dynamics · what is', 'Blocks · what is controlled', 'Process · what happened'. Keep the hover titles. At 390 px the second half may wrap under the first.
- **Acceptance:** The three toggle buttons' visible text contains 'what is', 'what is controlled' and 'what happened' at 1440 px and at 390 px.
- **Stories:** G1
- **Evidence:** story-6-g1-home.png, ixdb-tf-home.png, ixdb-job-guide1.png, ceb-guide-1.png

#### Q04. No leftover '…' in a panel

- **Pages:** /diagram side panel (system panel, stock panel, loop panel)
- **Problem:** The system panel shows a lone '…' under its title; the loop panel shows 'When it drives the behaviour …' for good; both read as a stuck load.
- **Change:** Show the description, or nothing. While a value is being worked out say 'being worked out'; when it cannot be, say why ('no loop is dominant in this window').
- **Acceptance:** After 10 s on :8796, clicking the product box, the users stock and marker R2: no element in the side panel has text equal to '…' or ending in ' …'.
- **Stories:** A4, G4
- **Evidence:** ixd-tf-into-click-stock.png, ixd-tf-into-click-loop.png, ixdb-sq-measure-click.png, pm-sf-click-users.png, sreb-is-measure-click.png, story-6-g4-R2.png

#### Q05. The navigation shows every page at phone width and at 200% zoom

- **Pages:** all pages, header
- **Problem:** At 390 px and at 720 px the tab strip is cut at 'Mode…'; Check and Guide are off-screen with no cue. The Guide, the only explainer, cannot be found on a phone.
- **Change:** Below 760 px wrap the tabs onto two rows (no sideways scroll). Keep the current page underlined.
- **Acceptance:** At 390x844 and 720x450 every one of the eight nav links has its bounding box fully inside the viewport, and document.scrollingElement.scrollWidth equals its clientWidth.
- **Stories:** A3, H4, H5
- **Evidence:** story-0-a3-phone-home.png, story-7-h4-phone-light.png, story-7-h5-zoom200.png, a11y-8792-zoom200-diagram.png, newcomer-blind-sf-phone-diagram.png

#### Q06. Guide's last frame uses the theme's box fill, and says it is loading

- **Pages:** /guide?frame=12
- **Problem:** In light mode the system dynamics thumbnail draws boxes as solid black with unreadable text; arriving by the arrow, the frame is blank for 1 to 2 s with no text.
- **Change:** Draw the thumbnail with the page's theme tokens (the same fill as the live diagram). Until both thumbnails have rendered show 'Drawing your system…' on the stage.
- **Acceptance:** At /guide?frame=12 in light mode every system-box rect in the left thumbnail has a computed fill equal to the live diagram's box fill, and its text contrast is at least 4.5:1; 200 ms after pressing → from frame 12 the stage contains visible text.
- **Stories:** A3
- **Evidence:** story-0-a3-light-13-wait.png, story-0-a3-dark-13.png, newcomer-briefed-guide-13.png, ixdb-job-guide12.png, ceb-guide-12.png, sdxb-guide-13.png

#### Q07. Guide frames stack their two diagrams on a narrow screen

- **Pages:** /guide (frames 2 and 13)
- **Problem:** At 390 px the two diagrams sit side by side at about 3 to 5 px text.
- **Change:** Below 760 px place the two diagrams one above the other at full width.
- **Acceptance:** At 390x844 on frames 2 and 13 the two diagram containers have different top offsets and each is at least 340 px wide; the smallest rendered text in them is at least 9 px.
- **Stories:** A3
- **Evidence:** story-0-a3-phone-02-wait.png, story-0-a3-phone-13-wait.png, a11y-8797-phone-guide.png, sdx-guide-02-phone.png

#### Q08. Guide sections and step dots are links

- **Pages:** /guide
- **Problem:** Section names ('Control: what we control', 'Yours') do nothing; dots are 12 px targets named only by title, with the current step shown only by fill.
- **Change:** Section names jump to their first frame. Dots get a 24 px hit area, aria-label 'Step n of 13' and aria-current='step'.
- **Acceptance:** Clicking 'Control: what we control' changes ?frame to that section's first frame; each dot's clickable box is at least 24x24; exactly one dot has aria-current='step'.
- **Stories:** A3, H5
- **Evidence:** ce-guide-control.png, a11y-8791-guide.png, ixd-tf-phone-guide.png

#### Q09. An unknown address gives a page with the navigation

- **Pages:** any unknown path, /item/<unknown>
- **Problem:** /nonsense returns a bare monospace 'not found' with no header and no way back; an unknown item page polls for ever.
- **Change:** Serve unknown paths inside the normal page frame: 'Nothing at this address', with a link to the Diagram. An unknown item stops polling after its first answer.
- **Acceptance:** GET /nonsense returns 404 and the page contains the eight nav links and a link to /diagram.
- **Stories:** A5
- **Evidence:** story-0-a5-nonsense.png, ixd-job-404.png, newcomer-blind-job-missing-item.png

#### Q10. A view with nothing to draw says so on the canvas

- **Pages:** /diagram?view=process (big); /diagram top level of big
- **Problem:** The Process view on big is a blank canvas: its empty-state text sits at y=900, below the canvas. The line 'No flows at this level: what crosses between these systems is information only' is drawn at y=−14 and never seen.
- **Change:** Centre the empty-state text in the canvas at every width, with the reason and where to look instead ('No kinds of item in big: its parts are counted by sensors. See Dynamics.'). Draw the 'No flows at this level' line under the boxes.
- **Acceptance:** On :8797/diagram?view=process at 1440x900 an element containing 'No kinds of item' lies wholly inside the canvas's bounding box; on :8797/ the text 'No flows at this level' has y within the viewport.
- **Stories:** A5, H1
- **Evidence:** story-0-a5-process.png, story-7-h1-process.png, infodb-big-process.png, ixdb-big-process.png, sre-big-process-fit.png, pm-big-process-12s.png

#### Q11. Open, Into and every panel link show that something is happening

- **Pages:** /diagram (Open, Into, links that open a panel), /loops, /items
- **Problem:** After Into the canvas and the side list stay fully blank for 1 to 5 s; the 'fixer' link takes 3 to 4 s with no cue; Loops and Items show only their heading while loading. All read as a crash.
- **Change:** Keep the old diagram, dimmed, until the new one is ready, and draw 'Opening api…' on the canvas at once. Never blank the side list. A panel opening shows its title and 'Loading…'. Loops and Items show 'Loading…' under the heading.
- **Acceptance:** 300 ms after clicking Into on api (:8797) the canvas contains visible text and the side list is not empty; 300 ms after clicking the 'fixer' link in a goal's evidence the panel region contains 'fixer'.
- **Stories:** A5, H2
- **Evidence:** story-0-a5-into-300ms.png, story-0-a5-into-2500ms.png, ixd-tf-diag-open-factory.png, ixd-big-into-api.png, story-2-c3-fixer-panel.png, pm-job-loops.png, story-6-g2-blk-quality.png

#### Q12. No command, YAML line or SPEC section on the reader's pages

- **Pages:** /diagram side panel, /loops, /agents, /items, loop and controller panels
- **Problem:** Reader pages tell people to run a command or edit configuration: '`ergostat actions` lists them', '(SPEC §9.7)', '(SPEC §12e)', 'a kind declares them under relations: (blocked_by: ticket)', 'write it in the goal's process:'. People only read here.
- **Change:** Replace each with what the reader can see or do: the waiting acts are listed in the row itself; 'These items do not wait on one another, so there is no critical path'; drop the SPEC references; the Harris row says what is missing ('needs the loop's dead time'). Absolute log paths in an agent's panel shorten to the file name.
- **Acceptance:** On all six demos the text of /diagram, /loops, /agents and /items (and any panel opened from them) matches none of: /SPEC §/, /ergostat\.yaml/, /`ergostat /, /relations:/, /under with:/, /\/private\/tmp/.
- **Stories:** A4, F5, G7
- **Evidence:** story-0-a3-home.png, story-0-a4-agents.png, story-0-a4-items.png, story-5-f5-tf-timeline.png, newcomer-briefed-tf-timeline-full.png, ixd-big-items.png, story-6-g7-tuner.png

### The system before ergostat's own upkeep

#### Q13. modelling is drawn last, set apart and labelled

- **Pages:** /diagram top level (Dynamics and Blocks)
- **Problem:** In every demo ergostat's model of its own upkeep is the top-left box, read first, unexplained and unconnected. A newcomer concludes the product is about itself.
- **Change:** Lay modelling out last (bottom right), with a dashed outline and the line 'ergostat's upkeep of this model, not the system'. Same place in Blocks, below a thin rule.
- **Acceptance:** On :8796/ and :8797/ in both views the modelling box's top-left corner is below or right of every other system box, its outline has a stroke-dasharray, and it contains the words 'upkeep of this model'.
- **Stories:** A2, B6
- **Evidence:** story-0-a2-home.png, pm-big-home.png, ixdb-sf-home.png, infodb-sf-home.png, ceb-annotated-sf-top.png

#### Q14. The headline counts the system's goals, and the model's upkeep apart

- **Pages:** header on all pages; project switcher
- **Problem:** '2 loops off' in red on software-factory and the-job is entirely modelling's own two goals; every demo is permanently red, so red stops meaning anything.
- **Change:** Header reads '0 goals off · model upkeep 2' (the second part in the muted colour, not red). The switcher uses the same definition, and states unknown goals separately ('7 off, 1 unknown') instead of adding them.
- **Acceptance:** On :8796 with only requests-handled and model-fits off the header's first figure is 0 and is not red, and the text 'model upkeep 2' is present; the switcher entry for a demo read from another demo shows the same first figure as that demo's own header at that moment.
- **Stories:** A2, B2
- **Evidence:** story-0-a2-home.png, story-0-a2-modelling-into.png, pmb-job-loops.png, pmb-sf-loops.png, ceb-tf-home.png, story-1-b1-home.png

#### Q15. A system alone at its level opens, whatever modelling does

- **Pages:** /diagram top level (the-job)
- **Problem:** The-job's README says the page opens with 'job' open; it opens as two closed boxes because modelling counts as a sibling. The stock-and-flow diagram is three levels down.
- **Change:** When the level holds one system besides modelling, start with that system open.
- **Acceptance:** On :8792/ at first load the 'job' system is open (its ten domains are drawn as boxes) and modelling is closed; a stock of 'incidents' is reachable in at most two clicks.
- **Stories:** A1, H2
- **Evidence:** story-0-a1-home.png, pmb-job-home.png, infodb-job-open.png, ixdb-job-sd-open.png, story-7-h2-thejob-into-job.png

#### Q16. Every name in a list carries its system

- **Pages:** /loops, /diagram side list and Suggestions, request item pages
- **Problem:** requests-handled, model-fits, unanswered-requests and the suggestions carry no system anywhere; Loops has no system column or grouping. On big the off goal's system is found only by going Into modelling.
- **Change:** Group the Loops rows under system headings (modelling last, collapsed). In the side list and Suggestions write 'modelling · requests-handled'. Inside a system's own view use the short name ('q0', not 'api-q0'). On a request's item page 'about: stock.api-q0' is a link to that part on the diagram.
- **Acceptance:** On :8797/loops every row sits under a heading naming its system; each side-list entry's text starts with a system name followed by ' · '; inside ?system=api no stock label starts with 'api-'; the request page's 'about' value is a link whose href contains 'system=api'.
- **Stories:** H3, A2
- **Evidence:** story-0-a2-loops.png, story-7-h3-loops.png, story-7-h3-attn-request-click.png, story-7-h3-click-loop.png, sreb-big-home.png

### Health and numbers that agree

#### Q17. The headline count is a link to the goals it counts

- **Pages:** header on all pages; /loops
- **Problem:** '2 loops off' is a red span among links; clicking it does nothing on any page.
- **Change:** Make it a link to /loops?status=off, which shows only those goals and says so with a 'show all' link.
- **Acceptance:** The header count is an <a>; clicking it from /items lands on /loops?status=off, where the number of rows equals the number in the link.
- **Stories:** B2, C1, H6
- **Evidence:** story-1-b2-headline-click.png, story-2-c1-click-loopsoff.png, story-4-loopsoff-click.png, story-7-h6-newtab.png

#### Q18. A goal's behaviour label does not flip between reloads, and flapping has a name

- **Pages:** /loops, loop detail
- **Problem:** Labels flip with no change of state ('within its bound' → 'past its bound 4%' → 'within its bound'); 'past its bound 0%' contradicts itself; a goal that crossed its bound 23 times in 32 minutes reads 'holding … Oscillating: no'; 'time off 0%' sits beside 'past its bound 5%'.
- **Change:** Apply hysteresis to the behaviour class (it changes only after the new class has held for a set share of the window). Write '<1%', never '0%', for a non-zero share. When crossings pass a threshold the label is 'flapping (23 crossings in 32m)'. Show one share in the row ('time off'), and define 'past its bound' beside it in the detail.
- **Acceptance:** Five reloads of :8791/loops in 60 s: any goal whose status did not change keeps the same behaviour text; no cell contains '0%' next to 'past'; on :8797 a goal with 20 or more crossings in the window shows the word 'flapping' and its count.
- **Stories:** B2
- **Evidence:** story-1-b2-loops.png, story-1-b2-loop-detail.png, sre-big-loop-osc.png, ce-big-loops.png

#### Q19. The window in the header never claims more than the record

- **Pages:** header window menu; /loops footnote; charts
- **Problem:** The header says 'Last 1h' while 33 minutes are recorded; percentages such as 'off 93% of the time' look heavier than the data supports.
- **Change:** When the record is shorter than the window the header reads 'Last 1h (33m recorded)', and every 'of the time' figure says 'of the 33m recorded'.
- **Acceptance:** On a demo started less than an hour ago the header window control contains 'recorded' and a duration; a suggestion containing '% of the time' also contains 'recorded'.
- **Stories:** B5
- **Evidence:** story-1-b5-signups.png, pm-tf-loops.png, pm-road-timepicker.png, infod-tf-items.png

#### Q20. One rate per flow, with its window, the same in three places

- **Pages:** /diagram Dynamics labels; stock and flow panels
- **Problem:** signups shows 13.2 on the diagram, 8.57 in the chart heading and 13.2 'over the window' in the table; users' inflow shows 9.31 and 13.2/min. None but one names its window.
- **Change:** The flow's figure is its mean over the header's window, shown identically on the diagram, in the chart heading and in the table, with a suffix ('13.2 users/min, mean of 33m'). If the latest value is also shown it is on its own row labelled 'now (last 15 s)'.
- **Acceptance:** On :8796 ?system=product, for signups and churn: the number on the diagram label, in the panel's chart heading and in its table 'Rate' row are equal as text, and each is followed by a window; the users panel's Inflow equals signups' figure.
- **Stories:** B5
- **Evidence:** story-1-b5-product.png, story-1-b5-signups.png, story-1-b5-users.png, sdxb-8796-users.png, sdxb-8796-churn.png, pmb-sf-users-stock.png

#### Q21. Rates in one system share one time base, and no value prints a bare '1'

- **Pages:** /diagram Dynamics; stock and flow panels; loop panel
- **Problem:** 'address 6.29 tickets/min' beside 'work 40.4 tickets/h' in one box; 'Inflow 18.1/day, Outflow 0/h' in one panel; 'model-error 0.951 1' and 'u … 1' print the dimensionless unit as a second number.
- **Change:** Choose one time unit per system (the one that suits its median rate) and use it for every rate drawn or listed for that system. Hide the unit '1'; the u axis prints its unit ('1 run').
- **Acceptance:** On :8791 ?system=factory all rate labels end in the same '/h' or '/min'; no diagram label or panel value matches /\d 1$/ on :8791 ?system=modelling.
- **Stories:** B5
- **Evidence:** ce-tf-dyn-factory.png, ceb-tf-home.png, sdx-8791-stock-model-error.png, infodb-sf-modelling-into.png, story-1-b3-users-detail.png

#### Q22. A system's loop count is the same on its box, in its panel and in its parent

- **Pages:** /diagram Dynamics: system boxes, system panel, 'Feedback loops' list
- **Problem:** product: 18 on the box, '16 inside and 13 through it' then '18 inside it or through it' in the panel; Everything: 34 against 11+18+18; factory 36 on the box, 47 in the panel; '18 loops, 6 reinforcing, 11 balancing'.
- **Change:** One definition everywhere: a system's count is the loops with at least one part inside it. The panel prints it once ('18 feedback loops: 5 through other systems'). A parent's count is the de-duplicated union, with '13 cross systems' when the parts' counts sum to more. R + B always equals the total (unsigned loops counted as '? n').
- **Acceptance:** On :8796 the count in product's panel heading equals the count in the 'Feedback loops' list for ?system=product; at Everything the panel states the total and the number crossing systems; reinforcing + balancing + unsigned equals the total.
- **Stories:** B5, G1
- **Evidence:** story-1-b3-home.png, story-6-g1-home.png, story-6-g6-click-factory.png, sre-tf-flow-click.png, sre-big-api-click.png, infodb-dark-sf-factory-open.png

#### Q23. A goal's bound is written the same way everywhere

- **Pages:** /diagram side list (Dynamics), stock panel, /loops
- **Problem:** Dynamics writes 'desired unanswered-requests = 0' for a ≤ 0 limit and 'desired quality = 0.93' without its ±0.01; the chart says '≥ 180' while the table says '= 180'. '=' states something false for a one-sided goal.
- **Change:** Build every mention from the goal's own bound text: 'desired users ≥ 180', 'desired quality 0.93 ±0.01', 'desired unanswered-requests ≤ 0: 37 over'. The magnitude is positive with a word for the direction ('over', 'short'); the signed e stays in Blocks and the scope.
- **Acceptance:** On :8793/ no side-list entry for a ≤ or ≥ goal contains '= '; quality-held's entry contains '±0.01'; on :8796 the users stock panel's 'Desired level' row contains '≥ 180'.
- **Stories:** B1, B5, G5
- **Evidence:** story-1-b1-home.png, story-1-b1-blocks.png, story-1-b5-users.png, infod-tf-home.png, ce-tf-loops.png, ixd-tf-loops.png

#### Q24. A stock's panel never says nothing acts on a goal that has an actor

- **Pages:** stock panel (Dynamics)
- **Problem:** users: 'desired users = 180 (nothing in the model acts on its gap: no feedback closes it)' while Loops lists users-growing, moved by product-manager, and the stock is in 13 loops.
- **Change:** The 'Desired level' row names the goal and what serves it ('goal users-growing, served by product-manager in factory'). Say 'nothing acts on its gap' only when the goal has no controller anywhere.
- **Acceptance:** On :8796 the users stock panel contains 'users-growing' and 'product-manager' and does not contain 'nothing in the model acts'.
- **Stories:** B5, C3
- **Evidence:** story-1-b5-users.png, sdx-8796-users.png, sdxb-8796-users.png, sdxb-8796-loops.png

#### Q25. Each polarity sign sits on its own arrow, and every top-level link has one

- **Pages:** /diagram Dynamics, links between systems
- **Problem:** Signs are stacked at the receiving edge where 7 to 15 links converge; the nearest sign is the wrong one (missing-ops → filed-features read backwards); deployed → shipped has no sign; driven-by links are solid though the README says dashed.
- **Change:** Place each sign beside its own arrowhead, offset along that link, at 13 px or more, never within 10 px of another sign. Give every drawn link a sign or a '?'. Draw driven-by links dashed.
- **Acceptance:** On :8796/ and :8793/ no two polarity glyphs' boxes overlap or lie within 10 px; each glyph's nearest link path is the link it belongs to (data attribute); every link has a sign glyph.
- **Stories:** B6, G3
- **Evidence:** story-1-b6-zoom.png, story-1-b3-home.png, infod-is-diagram.png, infodb-is-home.png, a11yb-8793-dynamics-light.png, a11yb-8791-into-factory-dynamics.png

### Why a goal is off

#### Q26. Every goal name is a link to its evidence, and the part is marked

- **Pages:** /diagram side list and Suggestions; /loops
- **Problem:** The red bold goal name in Needs attention, the bold name under Suggestions and (by keyboard) the Loops rows do nothing; only a small 'Evidence' link works. Opening evidence marks nothing in the diagram.
- **Change:** Every goal name is a button that opens the same evidence panel 'Evidence' opens, and rings the goal's stock (Dynamics) or its summing junction (Blocks), opening the system that holds it if needed. On Loops the name is a button.
- **Acceptance:** On :8791/ clicking the name of an off goal in the side list opens a panel whose title is that goal, and one diagram element gains the selection ring; on /loops the first cell of each row is a focusable button and Enter opens the panel.
- **Stories:** C1, H3, H5
- **Evidence:** story-2-c1-click-attention-name.png, story-2-c1-evidence.png, story-2-c1-blocks-evidence.png, story-7-h3-attn-loop-click.png, pm-tf-click-loop-attention.png, a11y-8791-loops.png

#### Q27. A system box that holds an off goal says so, without colour alone

- **Pages:** /diagram, closed and open system boxes, Dynamics and Blocks
- **Problem:** On big, billing and web held off goals and looked like every other box; in Blocks nothing is marked off at any level. The reader maps names from the side list to boxes by eye.
- **Change:** In the box's title row print '1 off' (the word, in the alarm colour) and draw the outline heavier. In Blocks print 'off: 1 of 4' as text under the block name; lines stay monochrome.
- **Acceptance:** On :8797/ in both views, each system whose goals include one with status off contains the text matching /\d+ off|off: \d/ and has a stroke-width greater than a holding system's; systems with none do not.
- **Stories:** C1, H1, B1, G6, H5
- **Evidence:** story-2-c1-factory-dyn.png, story-2-c6-big-dynamics.png, story-7-h1-home.png, story-7-h1-blocks.png, sre-big-diagram.png, infod-big-web-into.png

#### Q28. The evidence says in one line whether the actor was commanded, ran and moved anything

- **Pages:** goal evidence panel; /agents rows of rules
- **Problem:** requests-handled: 'u: never opened. Its valve did not open' beside 'Moves requests-answered 1.62/h' and a suggestion to do 'more per run'; Agents shows fixer with 34 runs; the Record shows it commanded every minute; its log says 'no open request the rule tier answers'. keep-requests-handled reads 'no roles, not run here'. A sensor reads 'unfilled' beside 'read 2s ago: 36'.
- **Change:** Build the actor lines from the same counts Agents and the Record use: 'fixer: commanded 34 times, ran 34, moved nothing (its log: no open request the rule tier answers)'. Show 'Moves' only for what this goal's own valve moved. When it moved nothing the suggestion says 'acts but moves nothing', not 'more per run'. Give each keep-* rule its controller role on Agents. Drop 'unfilled' when a reading exists.
- **Acceptance:** On :8791 the evidence for requests-handled contains 'commanded' and 'ran' with numbers equal to the fixer's run count on /agents for the same window; it does not contain both 'never opened' and 'Moves requests-answered'; the Agents row keep-requests-handled contains 'controller'.
- **Stories:** C3, C2
- **Evidence:** story-2-c1-evidence.png, story-2-c3-fixer-link-retry.png, story-2-c3-agents.png, story-2-c3-record.png, ceb-tf-fixer-panel.png, newcomer-briefed-tf-evidence.png, pm-sf-users-evidence.png

#### Q29. The evidence gives how long the goal has been off against how long it usually takes

- **Pages:** goal evidence panel; /loops 'back in' column
- **Problem:** The length of the current episode is never given (the reader subtracts a crossing time from the clock); 'back in' is '–' while off; 'Not worked out: it has no one process' says nothing the reader can use.
- **Change:** First line under the status: 'Off for 1m10s · usually back in 30s (slowest 41s, 4 times)', with 'longer than usual' when it is. 'back in' while off reads 'expected about 04:12'. Replace 'no one process' with its consequence: 'no single process to predict recovery from; using its past recoveries'.
- **Acceptance:** For an off goal on :8792/loops the panel contains 'Off for' with a duration and 'usually back in'; neither the panel nor the Loops table contains 'no one process'.
- **Stories:** C2, C4
- **Evidence:** story-2-c2-evidence-off.png, story-2-c4-located-worked.png, sreb-job-loop-panel.png, sre-big-loop-osc.png

#### Q30. A goal a person serves links to that person's waiting ask; a goal an agent serves links to its items

- **Pages:** goal evidence panel
- **Problem:** tickets-within-sla is served by a person, yet the evidence does not say whether anyone was asked and has no link to the ask; no goal's evidence links to the items its agent holds.
- **Change:** Under the actor: 'Waiting on: person/run-commands@2066, asked 6m ago' (a link to that entry) or 'no one has been asked'. For an agent: 'holding: ticket/SCRUM-7 (leased 03:26, 40s left)' as links.
- **Acceptance:** On :8792 the evidence of a person-served off goal contains either a link whose href includes 'person/' or the text 'no one has been asked'; on :8791 the evidence of a goal whose agent holds a lease contains a link to /item/.
- **Stories:** C2, C4
- **Evidence:** story-2-c2-evidence-off.png, story-2-c2-run-commands.png, sreb-job-loop-panel.png, story-2-c4-items.png

#### Q31. From a crossing to the Record, narrowed to that goal and time

- **Pages:** goal evidence panel; /record
- **Problem:** Crossings and Decisions rows are not clickable; the Record filters by event type only, so a goal or agent name answers 'Nothing recorded yet.'; the filter is not in the address.
- **Change:** Each crossing row links to /record?about=<goal>&from=…&to=…, which shows events of the goal, its controller, its actor and its valve. The filter box also matches item and source. The filter and the window live in the address.
- **Acceptance:** On :8797 clicking a crossing of billing-q0-low lands on /record with 'about=' in the URL and only rows whose type, item or source belong to that goal; typing 'fixer' on :8791/record shows rows; reloading the URL keeps the filter.
- **Stories:** C5, H6
- **Evidence:** story-2-c5-evidence.png, story-2-c5-crossing-click.png, story-2-c3-record-q-fixer.png, story-2-c5-record.png

#### Q32. A filter that matches nothing says so, with a way to clear it

- **Pages:** /record, /items
- **Problem:** The Record answers 'Nothing recorded yet.' to a filter that matches nothing. On Items 'Nothing matches.' is printed about 3000 px down, under every chart, so the search seems to do nothing; the chart and heading still show all items.
- **Change:** Record: 'Nothing matches "x" · clear'. Items: print the match count or 'nothing matches' beside the search box, and hide kinds (with their charts) that have no match while a search is active.
- **Acceptance:** On /record with filter 'zzz' the page contains 'Nothing matches' and a control that empties the filter; on :8791/items typing 'zzqx' shows 'nothing matches' within 100 px of the search box and no chart; typing 'SCRUM-2' shows '1' beside the box and one ticket row.
- **Stories:** C5, F1
- **Evidence:** story-2-c5-record-zzz.png, ixd-job-record-empty.png, story-5-f1-search-nonsense.png, story-5-f1-search-scrum2.png, ixd-job-items-search-nomatch.png

#### Q33. The Record folds runs of identical events

- **Pages:** /record
- **Problem:** On ticket-factory the Record is mostly 'auxiliary.set team-reviewing teammate {"value":0}' every 5 s, which buries the one-a-minute 'block.commanded fixer'.
- **Change:** Consecutive events with the same type, source, item and data become one row with '×N' and the first and last time; clicking it lists them.
- **Acceptance:** On :8791/record no two adjacent rows have identical type, source and data text; a row containing '×' followed by a number exists.
- **Stories:** C5
- **Evidence:** story-2-c5-record.png, sreb-tf-record.png

#### Q34. One time format everywhere, with the date and the zone

- **Pages:** /record, loop panel crossings, /items, /item/…, request pages
- **Problem:** Four formats, one with a zone: '04:04:36' (Record), '11/22/2026, 03:27:22' (item), 'Nov 22, 03:55' (list), '2026-11-22T11:22:55Z' (a field, 8 h away). Fields print epoch seconds as '1,795,346,621'; event data rounds them to 6 digits ('1795350000').
- **Change:** One formatter: '2026-11-22 04:03:55 PST' (the zone's short name; the date dropped only inside a table whose caption gives it). Format every *_at, raised, since and started field with it. Print event data unrounded.
- **Acceptance:** On /record, /item/ticket%2FSCRUM-2 and a goal's Crossings every time matches /\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S+/ or sits in a table whose caption carries the date and zone; no cell matches /1,7\d\d,\d{3},\d{3}/; 'done_at' in Events equals the field's value.
- **Stories:** C5, F2
- **Evidence:** story-2-c5-record.png, story-2-c5-item-page.png, story-5-f2-fields.png, story-5-f2-scrum2.png, story-7-h3-attn-request-click.png, sre-tf-item.png

#### Q35. Doubt about a stock is drawn on the stock

- **Pages:** /diagram Dynamics; side list
- **Problem:** The page already holds rings on stocks whose change the flows do not explain, but they are display:none. The only statement is a side-list line with no unit or window ('changed 0, the known flows explain 142: −142 unexplained'), shown as an operational alert.
- **Change:** Show the mark in the diagram's own idiom: a dashed outline on the stock and, under its value, '−1 ticket unexplained in 44m'. Add one line to 'How to read it'. Move the side-list line to the model-housekeeping group, written 'Δ stock = in − out + residual' with unit and window.
- **Acceptance:** On :8791 ?system=modelling a stock with a non-zero residual has a dashed stroke and a visible label containing 'unexplained', a unit and a duration; the same check passes on :8797; the legend contains 'unexplained'.
- **Stories:** C6
- **Evidence:** story-2-c6-modelling.png, story-2-c6-click-pending.png, story-2-c6-factory-all-open.png, sdx-8796-home.png, sdx-8794-home.png

#### Q36. The address holds what is selected and the window

- **Pages:** /loops, /diagram, /record, /items
- **Problem:** Selecting a goal or changing the window leaves the address at /loops; a pasted link shows no panel and 'Last 1h'. A stock selection on the diagram is not in the address. Changing the window closes the open panel and blanks the table.
- **Change:** Write ?select=, ?window= (and ?filter= on Record) with replaceState and read them on load. Changing the window keeps the panel open and shows 'Loading…' in the table.
- **Acceptance:** On :8797/loops select api-q2-low and choose Last 6 hours; opening location.href in a new tab shows the same panel and window; on the diagram selecting a stock adds 'select=' to the URL and a reload shows it ringed.
- **Stories:** H6, F4
- **Evidence:** story-7-h6-selected.png, story-7-h6-newtab.png, story-5-f4-back.png

### Agents and cost

#### Q37. Agents: a group heading counts its rows

- **Pages:** /agents
- **Problem:** The summary says '2 person → 4 ai → 13 program → 16 rule'; the headings below say '0 person', '1 ai', '4 program', '5 rule'. The heading number is the rung of the ladder, set exactly like a count. Seven reviewers read it as a bug.
- **Change:** Headings read 'person · 2', 'ai · 4' with the rung as small text ('rung 0, the most general'). The summary chips drop the arrows or say 'most general → most specific' once.
- **Acceptance:** On :8791/agents each group heading's number equals the number of rows under it and equals the summary line's number for that kind.
- **Stories:** D1
- **Evidence:** story-3-d1-agents.png, story-0-a4-agents.png, infodb-tf-agents.png, ixd-tf-agents.png, sreb-tf-agents.png, ce-tf-agents.png

#### Q38. Agents: each row says how it is engaged and which goal it serves

- **Pages:** /agents; agent panel
- **Problem:** A blank 'runs when' cell means on demand; the panel says 'Runs: not run by ergostat' beside '28 runs, 0 failed'; roles name valves, never goals ('valve work'); '0 failed' hides that most runs were refused.
- **Change:** 'runs when' reads 'on demand, per item (leased)' when blank. The panel line becomes 'started per item by its lease, not on a schedule'. Roles read 'valve work → goal located-worked'. The run tally reads '28 runs: 9 done, 19 refused (workspace pool full), 0 failed'.
- **Acceptance:** On :8791/agents no 'runs when' cell is empty; the 'work' row contains 'on demand' and a goal name; its panel does not contain 'not run by ergostat'.
- **Stories:** D1, D2
- **Evidence:** story-3-d2-work.png, story-3-d1-agents.png, pm-tf-agent-detail.png

#### Q39. An agent's recent runs name the item, the outcome and what it asked to do outside

- **Pages:** agent panel 'Recent runs'; /items Actions table; item 'Gated actions'
- **Problem:** Recent runs has no item, outcome or outward action and no links; its table is clipped at 1440 px. The Actions 'by' column is '–' for all 121 actions though each action page names its asker and approver.
- **Change:** Columns: when, item (link), outcome (done or refused, with why), outward actions asked (links), cost. Move CPU and memory behind a 'resources' disclosure so the table fits. Fill 'by' with the block that asked and 'approved by' with who answered ('owner (offline stand-in)').
- **Acceptance:** On :8791 the panel for 'work' lists at least three runs each with a link to /item/ and an outcome word, and the table's right edge is inside the panel; on /items?kind=ergostat.action no 'by' cell is '–'.
- **Stories:** D2, E3
- **Evidence:** story-3-d2-work.png, story-3-d2-recent-runs.png, story-4-scrum2-actions.png, story-4-items.png, story-4-action-dark.png

#### Q40. Cost is stated, with its unit, or the page says why it is zero

- **Pages:** /agents; agent panel; item header
- **Problem:** Cost and tokens are '–' or '$0' for every agent with no reason; items show 'AI cost $0.0000'; there is no total; the words 'free stand-in' appear only on Check.
- **Change:** A cost cell for an agent on a stand-in reads 'free stand-in, $0'. Add a total row for the window. The item header shows 'cost $0 (stand-in)' as the sum of its sessions. Hide a column that is empty for every row.
- **Acceptance:** On :8793/agents no cost cell is a bare '–' or '$0'; the table's last row starts with 'total'; /item/hypothesis%2F1 has 'cost' in its header line.
- **Stories:** D3
- **Evidence:** story-3-d3-agents.png, story-3-d3-improver.png, story-3-d3-item-hyp1.png, pm-tf-agents.png

#### Q41. An agent that never ran, is behind schedule or last failed stands out

- **Pages:** /agents
- **Problem:** improver: '0 runs, never ran, every 3m' in the same grey as everything else, with no reason. judge: 'not run here' with a blank runs cell beside 'every 30s', while its panel says 10 runs (about 120 expected).
- **Change:** Mark such rows with a word in the alarm colour ('never ran', 'behind: 10 of ~120', 'last run failed') and a one-line reason under the row. The top line counts them ('2 behind schedule'). The list and the panel take their run count from one source.
- **Acceptance:** On :8797/agents the improver and judge rows each contain an element with the exception class and one of the three phrases; the page's top line contains 'behind schedule' or 'never ran' with a count; judge's runs cell equals its panel's count.
- **Stories:** D4
- **Evidence:** story-3-d4-agents.png, story-3-d4-improver.png, story-3-d4-judge.png, sre-big-agents.png

### The Inbox

#### Q42. Needs attention is three headed groups in a fixed order

- **Pages:** /diagram side list
- **Problem:** 'Needs attention 4' beside '2 loops off': one list mixes goals that are off, asks of a person, requests and model notes, told apart only by red or amber. On big 24 requests bury the one alarm.
- **Change:** Three headings, always in this order, each with its count: 'Waiting for you 3', 'Goals off 2' (the system's first, modelling's after a rule), 'Model housekeeping 25' (collapsed). Each entry starts with its state word ('off ·', 'unknown ·') so colour is not the only cue. The count in the header equals the 'Goals off' group.
- **Acceptance:** On :8791/ the side list has three headings in that order, each ending in a number; the 'Goals off' number equals the header's; no entry's kind is conveyed only by colour (each begins with a state or kind word).
- **Stories:** E1, B2, H5
- **Evidence:** story-4-home.png, story-4-big-home.png, story-1-b2-home-0.png, infod-big-diagram.png, a11y-8794-focus-ring.png, ixd-big-diagram.png

#### Q43. What waits for me is one step from every page, and first on a phone

- **Pages:** header on all pages; /loops at 390 px
- **Problem:** The waiting requests exist only on the Diagram page's side list; on a phone '/' opens Loops, which has no list at all, and on the Diagram the list starts at y=665.
- **Change:** Beside the goals count the header shows 'N wait for you', a link to /diagram#waiting, which scrolls to and focuses the 'Waiting for you' group. At phone width it is the first thing in the header.
- **Acceptance:** On /items, /agents, /loops and /record at 1440 and 390 px a link containing 'wait for you' with the right number is in the first 200 px of the page; following it shows the 'Waiting for you' heading inside the viewport.
- **Stories:** E1, H4, A4
- **Evidence:** story-4-phone-job.png, story-4-phone-job-attention.png, story-7-h4-phone-diagram.png, story-4-loopsoff-click.png
- **Depends on:** Needs attention is three headed groups in a fixed order

#### Q44. A request reads as a sentence: what will happen, to what, who asks and why

- **Pages:** /diagram side list; action and request item pages
- **Problem:** Entries read 'person/approve@3156 approve is asked: Outward acts wait for your approval. `ergostat actions` lists them (and the p...', cut off; an action's first line is 'ran jira-transition, class jira-transition, gate approve' with the plain description buried in Fields; 'modelling holds no-unit on stock.api-q0 … the decision tier has no certain change for it'.
- **Change:** First line from fields the entry already has: '{description} {target}, for {item}, asked by {block} because {why}', for example 'Move SCRUM-7 to Done in Jira, for ticket/SCRUM-7, asked by close'. Person asks print in full (a <details> for anything past three lines). The exact command sits in a collapsed <details>. A modelling request reads 'api-q0 has no unit: modelling cannot decide one. Deny tells it to stop asking; the unit is yours to set through the Supervisor.'
- **Acceptance:** On :8792/ no entry under 'Waiting for you' contains '...' or a backtick; each has a first line ending before any 'python3'; the command is inside a closed <details>; every Deny-only entry contains a sentence starting 'Deny '.
- **Stories:** E2, A4
- **Evidence:** story-4-home.png, story-4-job-home.png, story-4-big-home.png, story-4-action-dark.png, story-4-job-request-item.png, newcomer-blind-tf-home.png, ixdb-tf-approve-item.png

#### Q45. A number or reason asked of a person has a full label and a unit

- **Pages:** /diagram side list inputs
- **Problem:** Inputs are 80 px wide with placeholders cut to 'how ma' and 'why (to de'. 'how many' has no unit; it appears even on a yes or no decision ('declare an incident?'). The reader cannot say what a typed number means.
- **Change:** A visible label above each input, from the ask: 'Ramps you decided (number)', 'Reason for denying (required)'. Inputs take the row's width. An ask whose answer is yes or no gets two buttons, not a number box.
- **Acceptance:** Every input in the side list has a visible <label> whose text is fully shown (scrollWidth ≤ clientWidth) and, for a number, names a unit; no placeholder is truncated.
- **Stories:** E2, H5
- **Evidence:** story-4-home.png, story-4-job-home.png, a11y-8791-home.png, a11y-8797-home.png, pm-tf-home.png

#### Q46. The vocabulary rewrite never touches an identifier

- **Pages:** /diagram side list (Dynamics wording)
- **Problem:** The Dynamics wording is a find-and-replace: 'queue-goal-tolerance on goal.ci-upgrade-planned' becomes 'queue-desired level-tolerance on desired level.ci-upgrade-planned', and 'a desired level's desired level and tolerance'. The same request reads 'decision tier' in one view and 'rule tier' in the other.
- **Change:** Translate only the sentence's own words, never codes, ids or part names (render them as separate tokens). The tier named comes from the request, not the view.
- **Acceptance:** On :8792/ in Dynamics the text of request/80fe1e93e1 contains 'queue-goal-tolerance' and 'goal.ci-upgrade-planned' or its plain name, and does not contain 'desired level.' or 'desired level-'; its text in Blocks names the same tier.
- **Stories:** E2
- **Evidence:** story-4-job-home.png, story-4-job-request-item.png, ixdb-job-sd-open.png, ixdb-job-blocks-incidents.png, sreb-big-home.png

#### Q47. The list holds still while I am in it, and a request stays until it is answered

- **Pages:** /diagram side list; /agents table
- **Problem:** With the pointer on the list the three requests were pushed out by new alarms within 24 s; a typed deny reason vanished with its request and focus fell to the body. On Agents a click opened a different agent because rows re-sorted between hover and click.
- **Change:** While the pointer or focus is inside the side list (or the Agents table) do not reorder or remove rows; show '3 updates waiting' at its top and apply them on leave. A request stays in place until answered or withdrawn, and then says so in its row.
- **Acceptance:** Hover the third request on :8792 for 40 s: its bounding box top changes by 0 px and it is still present; type in its reason box and wait 40 s: the text and focus remain. On /agents hovering a row for 20 s leaves the row order unchanged.
- **Stories:** E3
- **Evidence:** story-4-still-8792.png, story-4-typed-lost.png, sre-tf-attn-click.png, a11y-8793-agent-detail.png

#### Q48. Approve and Deny say what they answer, in an order the keyboard can use

- **Pages:** /diagram side list
- **Problem:** No button anywhere is labelled Approve where only person asks wait; buttons are 'Deny' and 'Done' with no object; Deny comes before its reason box in tab order, so the keyboard path denies before a reason can be typed; Deny is borderless beside a bordered Approve.
- **Change:** Buttons carry their object in the accessible name and, where it fits, visibly ('Approve the push', 'Deny the push'). Order in the row: sentence, reason field, Approve, Deny, with equal weight. Deny is disabled until a required reason is typed.
- **Acceptance:** Tabbing through a request reaches the reason field before the Deny button; each button's accessible name contains more than one word and is unique in the list; Approve and Deny have the same border style.
- **Stories:** E3, H5
- **Evidence:** story-4-kbd-deny-focus.png, story-4-big-home.png, ixd-tf-home.png, a11yb-8792-root.png

#### Q49. After I answer, the row says what was done and by whom, and the item shows it

- **Pages:** /diagram side list; /item/… 'Gated actions'
- **Problem:** Nothing confirms an answer; the item's Gated actions lines say 'ran 31m ago, gate approve' without by whom.
- **Change:** The answered row is replaced in place by 'Denied by you at 04:02, reason: … · see ticket/SCRUM-2' and stays until the next visit. The item's Gated actions line reads 'jira-transition: approved by owner (offline stand-in) 03:24, ran 03:24' or 'denied by … : reason'.
- **Acceptance:** After pressing Deny on a test request the row contains 'Denied by' and a link to the item; that item's page contains the same request with 'denied by'. Every Gated actions line contains 'approved by' or 'denied by'.
- **Stories:** E3
- **Evidence:** story-4-scrum2-actions.png, story-4-action-dark.png

#### Q50. Requests that are alike fold into one, with a count and one answer

- **Pages:** /diagram side list; /items 'Modelling requests'
- **Problem:** On big 24 'no-unit' requests each take a seven-line row with its own Deny; four fill the list; the one real alarm and everything else are pushed away. /model says 'Changes to review: Nothing waiting' at the same time.
- **Change:** Group by (code, asker): one <details> row '24 stocks have no unit (api, billing, build, data, support, web) · Deny all', whose body lists the members, each with its own control. /model's 'Changes to review' counts the same held requests.
- **Acceptance:** On :8797/ the side list has one entry containing '24' and 'no unit'; opening it lists 24 members; every other entry in the list is visible without scrolling at 1440x900; /model does not say 'Nothing waiting' while requests are held.
- **Stories:** E4, E1, H1
- **Evidence:** story-4-big-home.png, story-4-big-dark.png, story-4-big-model.png, sreb-big-home.png, ce-big-home.png, infodb-big-home.png

#### Q51. Per class of action: asked, approved, denied, and whether it is held

- **Pages:** /items › oversight › Actions
- **Problem:** No page states per-class totals. The tallies '0 requested, 0 approved, 121 ran, 0 denied' count present state, so '0 approved' misleads; '11 asked, 0 approved' for the person ask contradicts 121 actions approved by the stand-in. The Items search does not match the action field.
- **Change:** Above the Actions rows, one line per class: 'jira-transition: 24 asked, 24 approved (by the offline stand-in), 0 denied this week · held for approval'. The search matches class and command.
- **Acceptance:** On :8791/items the Actions section has a row starting 'jira-transition' with three numbers and either 'held for approval' or 'let through'; asked = approved + denied + waiting; typing 'jira-transition' in the search narrows the action rows.
- **Stories:** E5
- **Evidence:** story-4-actions-all.png, story-4-items-search-jira.png, story-4-action-dark.png

### Items

#### Q52. The Items table fits at 1440 px

- **Pages:** /items
- **Problem:** The ticket table's 'latest', 'last' and 'in state' columns are cut at the right edge ('ergos…', 'in s') with no scroll cue; pr_url takes the width.
- **Change:** Show pr_url as a short link ('PR #7'). If columns still overflow, wrap the row's secondary fields onto a second line. At phone width keep id, state and time in state.
- **Acceptance:** At 1440x900 on :8791/items every th's right edge is within the table container's right edge and no cell's text is clipped (scrollWidth ≤ clientWidth).
- **Stories:** F1
- **Evidence:** story-5-f1-items.png, story-0-a4-items.png, pm-tf-items.png, sre-tf-items.png, ixd-tf-items.png

#### Q53. An item's header and its latest change read as words

- **Pages:** /item/…; /items 'latest' column
- **Problem:** The header shows 'Latest ergostat.lease.ended, 28m ago'; the list's 'latest' column shows 'ergostat.item.joined' on every row; cost is buried in fields; 'Not held Attempts 0 of 3.' runs together; a live item reads 'State done for 4s' beside 'running in reviewer for 2s'.
- **Change:** Header is one sentence: 'done for 28m · held by nobody · cost $0 (stand-in) · 15 outward actions'. 'Latest' is the last change of state in words ('waiting for review, 3m'). The header's state is read at the same moment as the rest of the page.
- **Acceptance:** On /item/ticket%2FSCRUM-2 the header line contains the state, 'held by', 'cost' and 'outward actions', and no text matching /ergostat\.[a-z]+\.[a-z]+/; on /items no 'latest' cell matches that pattern.
- **Stories:** F2
- **Evidence:** story-5-f2-scrum2.png, story-5-f2-live-item.png, pm-road-items.png, ixd-job-item-detail.png

#### Q54. An item's history shows its states, not its leases

- **Pages:** /item/… 'How it moved', Lease table
- **Problem:** About half the rows of 'How it moved' are '→ leased' and 'leased →' pairs; the Lease table is 26 rows ending '(not counted)' before anything readable; on a phone it runs off the edge.
- **Change:** 'How it moved' lists changes of state only, with who or what made each in a 'by' column (from the lease). The Lease table is a collapsed <details> 'Attempts (26)'; '(not counted)' is explained once in its caption.
- **Acceptance:** On /item/ticket%2FSCRUM-2 no row of 'How it moved' has 'leased' as a state; the lease table is inside a closed <details>; '(not counted)' appears at most once.
- **Stories:** F2
- **Evidence:** story-5-f2-howitmoved.png, story-5-f2-phone-dark.png, newcomer-blind-tf-item.png, pm-tf-item-detail.png

#### Q55. The lifecycle strip shows the path taken, and does not draw alternatives as next steps

- **Pages:** /item/…
- **Problem:** The strip draws 'done → stopped → dead' and, on a session, 'open → done → failed → lost' with arrows, as if a done item can still fail. States ahead are 1.6:1 grey.
- **Change:** Draw the states this item passed through, joined by arrows, ending at its present state. Other endings sit apart with no arrow ('could also have ended: stopped, dead'), in muted text of at least 4.5:1. Final states carry a mark (a double border).
- **Acceptance:** On a done ticket no arrow element lies between 'done' and 'stopped'; every state label has contrast ≥ 4.5:1 in light and dark.
- **Stories:** F2, F6, H5
- **Evidence:** story-5-f2-scrum2.png, story-5-f6-session.png, a11y-8793-item-detail.png, infodb-sf-item.png

#### Q56. Every band of the state chart is labelled, in light and in dark

- **Pages:** /items (state chart per kind)
- **Problem:** Up to 17 states in about four near-identical greys with 8 px swatches; the largest state can be found only from the bold count in the legend; in dark mode the finished state becomes the brightest mass.
- **Change:** Label each non-empty band at its right edge with its state and count ('done 6'). Fold states that are zero over the whole window into '+9 empty states'. Finished states take an outlined or hatched fill instead of a darker grey. Keep the same lightness order against the background in both themes. Give the chart an aria-label summarising the counts.
- **Acceptance:** On :8796/items in light and dark each band with a count above zero has a text label within its vertical extent at the right edge; the legend has no entry with count 0; the chart svg has an aria-label containing the counts.
- **Stories:** F3, H5
- **Evidence:** story-5-f3-items.png, story-5-f3-items-dark.png, infod-tf-items.png, infod-dark-tf-items.png, a11y-8791-items-dark.png

#### Q57. From Items to the process map, and the map says how many are there now

- **Pages:** /items; /diagram?view=process (States)
- **Problem:** Where work queues is shown only on the Process map, which Items does not link to; the map's node counts are visits ('18× · 16 items'), not how many items are in the state now; node text is about 8 px at Fit.
- **Change:** Each kind's name on Items has a 'process map' link to /diagram?view=process&kind=<kind>&mode=states. In States mode each node shows 'now 3' before the visit count. The map fits at no less than 11 px text and says which way more lies.
- **Acceptance:** On :8796/items the ticket kind has a link whose href contains 'view=process'; on that map every node contains 'now ' and a number equal to the Items legend's count for that state; no node label is below 11 px.
- **Stories:** F3
- **Evidence:** story-5-f3-process-states.png, story-5-f3-process.png, story-5-f3-items.png, a11y-8796-process.png

#### Q58. An item says where it is counted in the model, with a link back

- **Pages:** /item/…
- **Problem:** The item page has no link to the stock it is counted in, its system or the diagram; the round trip from a stock works only by the browser's Back button.
- **Change:** In the header: 'counted in: done (factory › shipping)', a link to /diagram?view=dynamics&system=factory&open=shipping&select=stock/done.
- **Acceptance:** On /item/ticket%2FSCRUM-2 a link containing 'counted in' exists; following it shows the diagram with shipping open and the stock 'done' ringed.
- **Stories:** F4
- **Evidence:** story-5-f4-done-click.png, story-5-f4-back.png
- **Depends on:** The address holds what is selected and the window

#### Q59. Timeline draws each item's states over time, relations or not

- **Pages:** /items Timeline and Graph
- **Problem:** On demos whose items have no relations Timeline shows the same charts as List plus a configuration instruction, though its tooltip promises 'A Gantt chart: each item's states over time'. Switching mode barely changes the screen.
- **Change:** Without relations, Timeline draws one bar per item, split by state over time. Graph says 'These items do not wait on one another, so there is no dependency graph'. In both modes the mode's own content comes first, above the per-kind charts.
- **Acceptance:** On :8791/items?view=timeline one row per ticket (8) is drawn with segments labelled by state, within the first 900 px; the page does not contain 'relations:'.
- **Stories:** F5, F2
- **Evidence:** story-5-f5-tf-timeline.png, story-5-f5-tf-timeline-nofrontier.png, newcomer-blind-tf-items-timeline2.png, ixd-job-items-timeline.png

#### Q60. The finish estimate is a clock time that agrees with the critical path

- **Pages:** /items Graph and Timeline (roadmap)
- **Problem:** 'last of 1 epic done in about 1s (p90 1s)' appears seconds after the view, as a duration, beside 'critical path 5 items, done in about 15s'; the item page uses a third form. The Timeline lists 100+ epics oldest first, so the current one is three screens down.
- **Change:** One sentence, present on first paint (or 'being worked out'): 'last epic (e100) expected 04:02, by 04:03 at worst (9 in 10)', not earlier than the critical path's end. The Timeline opens scrolled to 'now' with finished epics collapsed.
- **Acceptance:** On :8794/items?view=graph the legend contains a clock time and 'at worst'; that time is ≥ now + the critical path's remaining duration; on Timeline the 'now' line is inside the viewport at load.
- **Stories:** F5, B4
- **Evidence:** story-5-f5-graph-legend.png, story-5-f5-graph.png, story-5-f5-timeline.png, story-5-f5-timeline-end.png, pm-road-graph.png

#### Q61. Each kind of item says what it is, and whether its items finish or live on

- **Pages:** /items; /item/…
- **Problem:** Kinds have no description; nothing says which complete and which stay; names mix 'hypothesis' with 'Claims' and 'ergostat.' ids. A finished session and a release both offer 'Send a note about this: it goes to the work on it now', above the item's facts.
- **Change:** Under each kind name: its one-line meaning and a tag, 'finishes (kept, dropped)' or 'lives on'. Built-in kinds get a plain name with one casing. 'Send a note' shows only on an item that is held or waiting, and sits below the header and history.
- **Acceptance:** On :8793/items every kind heading is followed by a description and one of the two tags; /item/release%2F2 and a done session contain no 'Send a note' control.
- **Stories:** F6
- **Evidence:** story-5-f6-items.png, story-5-f6-session.png, infodb-sf-item.png

### Two perspectives

#### Q62. In Dynamics a goal is called a goal; 'loop' means an R or B loop

- **Pages:** /diagram side list and Suggestions in Dynamics
- **Problem:** The Dynamics side list says 'loop requests-handled' directly above 'Feedback loops 18: R2, R3 …'. One word names a controlled goal and a causal loop in one panel; counts (49 against 16) look like double counting. Suggestions speak of 'its decision (fixer, every 1m)' in the SD view.
- **Change:** In Dynamics write 'goal requests-handled' and 'what serves it'. Keep 'Feedback loops' for R and B. In Blocks write 'control loop'. Where an R or B loop closes a goal, its row says 'serves goal model-fits'.
- **Acceptance:** On :8796/ in Dynamics no side-list entry or suggestion starts with 'loop '; the heading 'Feedback loops' remains; in Blocks the list heading reads 'Control loops'.
- **Stories:** G1
- **Evidence:** story-6-g1-home.png, sdxb-8796-blocks.png, ceb-tf-home.png, ceb-tf-blocks.png, a11yb-8791-blocks-light.png

#### Q63. What I selected stays selected, with its panel, when I switch view

- **Pages:** /diagram (Dynamics ↔ Blocks)
- **Problem:** Selecting the stock quality and switching to Blocks highlights the sensor H(s), not the process output, and the panel falls back to Needs attention. Clicking a flow's label opens 'Charts of the parts chosen' instead of its panel; in Blocks its panel is titled 'Valve'.
- **Change:** Keep the panel open across the switch, titled in the target discipline's words: 'output y_quality of P_service', 'actuating signal u_tuner', 'reference r = 0.93 and its summing junction'. Map a stock to y at the process output. A plain click on a flow's label opens the flow's panel.
- **Acceptance:** On :8793 ?system=service select stock quality, switch to Blocks: within 1 s the element y_quality at the process output has the selection ring and the side panel's title contains 'y'; clicking the label 'quality-steps' in Dynamics opens a panel whose title contains 'quality-steps'.
- **Stories:** G2
- **Evidence:** story-6-g2-blk-quality.png, story-6-g2-blk-quality-late.png, story-6-g2-dyn-quality-steps.png, story-6-g2-blk-desired_quality.png

#### Q64. A loop is called R or B only when every link has a sign

- **Pages:** /diagram Dynamics markers; loop panel
- **Problem:** R2 is 'Reinforcing' though 9 of its 12 links show no sign; one panel shows '(?)' for a link another shows as '+'. Rows mix 'stock:awaiting-deploy' and 'gap:all-live' with plain names. Markers carry an unexplained '+1'.
- **Change:** Fill the signs that hold by definition (inflow → stock +, outflow → stock −, stock → its gap +, desired → gap −). If any link is still unsigned the marker reads '?' and the panel says which link. One sign per link across panels. Plain names, all links. '+1' becomes '2 alike' with a title naming the other loop.
- **Acceptance:** On :8796 ?system=product every row of R2's 'Around the loop' table has + or −, or the marker's letter is '?'; no row text contains 'stock:' or 'gap:'; no marker text matches /\+\d$/.
- **Stories:** G3, G4
- **Evidence:** story-6-g4-R2.png, sdxb-8796-R3.png, sdx-8791-gap.png, sdx-8791-modelling-fit.png, story-6-g4-B1.png, newcomer-briefed-is-service.png

#### Q65. Every block carries a function, with the agent's name as its caption

- **Pages:** /diagram Blocks
- **Problem:** open-pr, work, fixer, judge, improver and the drains are drawn as name-only boxes; the law, or that none is stated, appears only on click. Decision 2 asks for a function in every block.
- **Change:** Main label is the function: the known law ('u = max(0, y − r/2)'), 'f(·), law not stated' for an unknown one, 'H = 1, every 3 s' for a counting sensor. The agent's name and kind go in small text above the block, where the kind badge is.
- **Acceptance:** On :8791 ?view=blocks&system=making every block's main label contains '=', '(s)', '(z)' or 'f(·)'; the texts 'open-pr' and 'work' appear only as captions outside or at the top of the box.
- **Stories:** G5
- **Evidence:** story-6-g5-blocks-making.png, story-6-g5-click-open-pr.png, ceb-tf-modelling-blocks-fit.png, ceb-big-api-blocks.png, infodb-sf-modelling-blocks.png

#### Q66. A one-sided limit is drawn and named as a limit

- **Pages:** /diagram Blocks; controller panel; /loops
- **Problem:** 'worked-opened ≤ 0' is drawn as 'r = 0' and called a setpoint; the error column shows 0 inside the bound with nothing saying why; a relay is 'with hysteresis' though its on and off thresholds are equal.
- **Change:** Label the reference 'r ≤ 0' and call it a limit in the panel and on Loops ('limit ≤ 20', 'setpoint 0.93 ±0.01'). The relay panel says 'ideal relay' unless it has a band, and the drawn glyph matches.
- **Acceptance:** On :8791 ?view=blocks&system=making the reference label of worked-opened contains '≤'; its panel contains 'limit' and not 'setpoint'; a relay whose thresholds are equal does not contain 'hysteresis'.
- **Stories:** G5
- **Evidence:** story-6-g5-blocks-making.png, story-6-g5-click-keep-located-worked.png, ce-tf-model-controller.png, ce-big-loops.png

#### Q67. Sensors polled alike are drawn alike

- **Pages:** /diagram Blocks
- **Problem:** In image-squeeze service 'bytes-per-mp, every 8 s' is 'H = 1' and 'quality, every 8 s' is 'H(s) = e^{-sT}, T = 8 s' with a sampler: one source, one period, two notations.
- **Change:** Draw every polled sensor with a sampler and its period; draw the sampler in the muted stroke when T is negligible against the loop's time constant and print the ratio in the sensor's panel.
- **Acceptance:** On :8793 ?view=blocks&system=service any two sensor blocks with the same period have the same main-label form and both have a sampler glyph.
- **Stories:** G5
- **Evidence:** ceb-is-service-into.png, ce-tf-blocks-oversight.png, ce-sf-blocks-product.png

#### Q68. The Blocks legend defines every symbol, and a name is printed once

- **Pages:** /diagram Blocks 'How to read it'; subsystem blocks
- **Problem:** 'Q' and the '3×1' dimensions are never defined; Q is bold on one level and italic on another; an opened subsystem reads 'Q_service  service'.
- **Change:** The legend adds the subsystem symbol in use and 'p×m: outputs × inputs (disturbances counted)'. One typeface for the letter at every level. Drop the repeated plain name beside the symbol.
- **Acceptance:** On :8796 ?view=blocks the legend contains '×' with the words 'outputs' and 'inputs' and defines the subsystem letter shown; no block contains its system's name twice; the letter's font-style and weight are the same at top level and inside.
- **Stories:** G6
- **Evidence:** story-6-g6-blocks-top.png, ceb-is-service-open.png, ce-sf-blocks.png, newcomer-blind-tf-blocks.png

#### Q69. A loop's panel starts with a table: law, process, held-out fit, performance

- **Pages:** controller and process panels (Blocks)
- **Problem:** The law follows prose and the performance figures; the process line is near the bottom; the fit reads 'Fit: 0% of the record held out, of the 0% its noise allows' and 'follows −128% held out' with the measure undefined; the quality-held panel ends with a paragraph about small-images; the matrix is cut at the panel's edge.
- **Change:** First: a table of law / process model with ±σ (or 'not identified: needs a step of u') / fit on held-out data ('NRMSE fit, 100% is perfect, below 0 is worse than the mean') for estimation and validation / time off / settling / saturation. Then the charts, then prose, with the step-test paragraph behind 'how it is sized'. Only this loop's text. The matrix scrolls sideways inside the panel; each <math> has alttext.
- **Acceptance:** On :8793 clicking C_tuner: the panel's first table precedes any <p> and has rows named law, process, held-out fit, time off, settling, saturation; the panel does not contain 'small-images'; the fit row names its measure; no math element's right edge exceeds the panel's.
- **Stories:** G7
- **Evidence:** story-6-g7-tuner.png, ceb-is-process-panel.png, ce-is-process.png, a11yb-8793-deadband-panel.png

#### Q70. The exported picture is fit for a document

- **Pages:** /diagram Export (PNG, SVG)
- **Problem:** The Dynamics PNG loses every loop name, turns connectors into dotted fragments where label halos were, cuts '225 users' and breaks links; the Blocks PNG has no legend and clips subscripts.
- **Change:** Rasterise from the same SVG the page shows (halos as paint-order strokes, fonts embedded), in light mode whatever the theme. Include title, date, window and the legend in both views.
- **Acceptance:** Export PNG of :8796 ?system=product: the image text (by OCR or by the intermediate SVG's text nodes) contains every loop name on screen and '225 users'; the Blocks export contains the legend's text; the background is white in dark mode too.
- **Stories:** G8
- **Evidence:** story-6-g8-export-dynamics-*.png, story-6-g8-export-blocks-*.png, story-6-g8-export-menu.png

### Large systems, small screens, every reader

#### Q71. Open frames what was opened, Fit includes every wire, and the edge hint says which way

- **Pages:** /diagram (Open, Into, Fit)
- **Problem:** After Open the opened system lands half off-screen under a large empty area; Fit still leaves wires and labels beyond the right edge; 'More beyond the edge' does not say where; the floating toolbar covers labels.
- **Change:** After Open or Into, pan and zoom so the opened system's bounds are in view (at no less than the minimum text size). Fit uses the bounds of every node, wire and label. The hint reads 'more to the right / below' and is clickable to pan there. Keep the toolbar off the drawing's bounds.
- **Acceptance:** On :8797 after Open on api, api's bounding box is wholly inside the canvas viewport or a hint naming a direction is shown; after Fit on :8791 ?view=blocks&system=modelling every path's and text's bounding box is inside the viewport and no hint is shown.
- **Stories:** H2, A5
- **Evidence:** story-7-h2-open-api.png, story-7-h2-open-api-fit.png, story-5-f4-open-1.png, ceb-tf-modelling-blocks-fit.png, ceb-is-service-open.png, newcomer-briefed-tf-factory-open.png

#### Q72. On a phone each goal is a card: value against bound, and how long off

- **Pages:** /loops at ≤ 760 px
- **Problem:** The table is 943 px wide in 358 px: loop, status and holds show; now, setpoint, error and time off are off to the right with no cue. 'Time off' is a share of the window, not how long the goal has been off.
- **Change:** Below 760 px each row is a two-line card: 'requests-handled · off' then '36 against ≤ 0 · off 36m · usually back in 30s'. Off goals first. No sideways scroll.
- **Acceptance:** At 390x844 on :8791/loops, in light and dark, each off goal's card shows its value, its bound and a duration within the viewport's width; the page's scrollWidth equals its clientWidth.
- **Stories:** H4
- **Evidence:** story-7-h4-phone-light.png, story-7-h4-phone-dark.png, story-1-phone-dark-loops.png, ce-tf-loops-phone.png, infodb-phone-sf-loops.png

#### Q73. On a phone the diagram opens fitted to the screen

- **Pages:** /diagram at 390 px
- **Problem:** At 390 px the canvas is blank on the-job (neither box in view), shows part of one box on software-factory, and opens mid-drawing inside a system.
- **Change:** On load and on every change of view at narrow width, fit the drawing to the canvas (down to the minimum text size, then centred on the first off part with a direction hint).
- **Acceptance:** At 390x844 on :8792/ and :8796/ at least one whole system box is inside the canvas viewport at load; on :8796 ?system=product the stock 'users' or a direction hint is visible.
- **Stories:** A1, H4
- **Evidence:** story-0-a1-home-phone.png, story-0-a2-phone.png, story-1-phone-dark-diagram.png, story-6-phone-dark-dyn-product.png, story-6-phone-blocks-making.png

#### Q74. Everything clickable in the diagram can be reached and acted on by keyboard

- **Pages:** /diagram (all views); side panel 'Feedback loops' rows
- **Problem:** Open, Into, stocks, flows, blocks and loop markers are SVG groups with no tabindex or role; Tab skips the diagram. The side panel's loop rows are divs. A keyboard or screen-reader user cannot open a system or read a block's definition.
- **Change:** Give each system box's Open and Into, each stock, flow, block and loop marker tabindex=0, role=button and an aria-label ('stock api-q0, 13, desired ≤ 20, holding'); Enter and Space do what a click does. Side-panel loop rows become buttons. Opening a panel moves focus to its heading; Escape returns focus to the part.
- **Acceptance:** Using only Tab, Enter and Escape on :8791/: focus reaches 'Open' on factory and opens it; reaches a stock and opens its panel with focus on the panel heading; Escape returns focus to that stock. Every element with cursor:pointer in the svg is focusable.
- **Stories:** H5
- **Evidence:** story-7-h5-loops-kbd.png, a11y-8791-home.png, a11y-8797-stock-click.png, a11yb-8793-into-service-block-click.png

#### Q75. The current page, view and mode are announced; tables and controls have names

- **Pages:** all pages
- **Problem:** Nothing carries aria-current or aria-pressed; tables have th cells in a body row and no caption; the Items h2 names include '▾'; a sort button is named 'Sort by by'; −, + and ⋯ are named by title only; /model rows end in identical 'process, controller, scope' links; the side panel is a div, not a landmark; several targets are under 24 px.
- **Change:** aria-current='page' on the nav; aria-pressed on Dynamics/Blocks/Process and on Items' List/Graph/Timeline; <thead>, scope and a caption on each data table; aria-hidden on glyphs; aria-labels 'Zoom out', 'Zoom in', 'More diagram options', 'Sort by author'; row name added to repeated links; side panel as <aside aria-label>; 24 px hit areas on Evidence links, legend links and the Record checkbox.
- **Acceptance:** axe-core on /diagram, /loops, /agents, /items, /record and /model reports no violations of aria-allowed-attr, button-name, link-name, th-has-data-cells or target-size; exactly one nav link has aria-current='page' and exactly one view button has aria-pressed='true'.
- **Stories:** H5
- **Evidence:** a11y-8796-process.png, a11y-8791-items.png, a11y-8791-model.png, a11y-8791-agents.png, story-7-h5-zoom200-tab-guide.png

#### Q76. 'Off' in a chart is a mark as well as a colour

- **Pages:** loop evidence scope charts; /item lifecycle; /agents tier arrows
- **Problem:** Off periods in the y/u/e charts are a pale pink (light) or maroon (dark) band keyed only by the text 'Red: off'; tier arrows and count arrows are 1.6:1.
- **Change:** Hatch the off bands and label them 'off' on the time axis; the key is a hatched swatch labelled 'off'. Raise arrows and Guide dot borders to at least 3:1.
- **Acceptance:** The scope's off bands have a pattern fill; the legend contains a swatch element with the same pattern and the word 'off', and no text 'Red: off'; computed contrast of tier arrows against the background ≥ 3:1 in both themes.
- **Stories:** H5
- **Evidence:** a11y-8791-loops-row-clicked.png, a11y-8791-loops-dark.png, a11yb-8793-into-service-block-click.png, a11y-8791-agents.png

#### Q77. New requests and a changed count are announced

- **Pages:** /diagram side list; header counts
- **Problem:** The page changed 21 times in 8 s with one polite live region in the whole product; a screen-reader user is never told a request is waiting.
- **Change:** The header counts and the 'Waiting for you' heading sit in an aria-live='polite' region that announces only a change of count ('1 new request waits for you').
- **Acceptance:** The element holding 'N wait for you' has aria-live='polite' (or is inside one) and its text changes only when N changes.
- **Stories:** H5, E1
- **Evidence:** a11y-8791-home.png, a11yb-8792-root.png
- **Depends on:** What waits for me is one step from every page, and first on a phone

### Model pages and the rest

#### Q78. Check and the Model page say each thing once, in a table

- **Pages:** /check, /model
- **Problem:** Check is 17 run-on sentences, 13 of them the same warning with different numbers, then 30 lines of 11 px grey prose joined by semicolons. Model repeats 'an integrator, from the model / its dead time: a step of u, or a step test' on nearly every row; its 'process, controller, scope' links are href='#' and land on an arbitrary place with every system open.
- **Change:** Check: one table per kind of warning (part, R² or 'never moved', scaled error, points), sorted worst first, the advice once above it, each part a link to the diagram; notes as a list at body size. Model: group rows with the same identification ('12 loops: an integrator, not yet tested'); each link opens that loop's panel with its system framed.
- **Acceptance:** On :8791/check no warning sentence longer than 80 characters occurs more than once; there is a table whose header includes 'R²'; on /model clicking 'process' for located-worked changes the URL to that loop's system and opens a panel whose title contains its process.
- **Stories:** C6, G7
- **Evidence:** infod-tf-check.png, infodb-sf-check.png, ixd-tf-check.png, a11y-8793-check.png, infod-tf-model.png, ceb-is-process-panel.png, sre-tf-model-process2.png

#### Q79. A flow with no value says why, and an estimate with no basis says so

- **Pages:** /diagram Dynamics; flow panel
- **Problem:** regressions, fixes, shipped and asks show a bare '–' on a live diagram; rates keep a value with nothing in flight; 'work-time 40m ± 2d' and 'Nothing says the value written is wrong' beside 0.404 ± 0.116 against a declared 2.
- **Change:** A flow that did not move in the window shows '0' with 'no movement in 33m' in its panel; one that is not measured shows 'not measured'. An interval wider than ten times its estimate prints 'not enough record yet'. When the declared value lies outside the interval say 'the record so far rejects 2 but cannot yet settle a value'.
- **Acceptance:** On :8796 ?system=product no flow label is a bare '–'; the churn panel does not contain 'Nothing says the value written is wrong' while the declared value is outside the estimate ± 3σ; no panel shows an interval more than ten times its estimate.
- **Stories:** B5, C6
- **Evidence:** sdx-8796-product-zoom.png, sdx-8796-churn-whatif.png, newcomer-blind-tf-making-click-flow.png, sreb-tf-home.png

#### Q80. A suggestion appears when it has a verdict

- **Pages:** /diagram side list Suggestions
- **Problem:** 'loop requests-handled was off 92% of the time; why (a flow too small to close the gap, or acting too seldom) is said after 10m of record (1m51s so far)': it names the goal twice, offers two causes and defers. The Agents page calls the same cause 'a valve too small'.
- **Change:** Hide a suggestion until its verdict exists; until then its goal's entry carries 'diagnosis in 8m'. Name the goal once. One phrase for the cause on every page.
- **Acceptance:** No suggestion contains 'is said after'; no suggestion contains its goal's name more than once; the cause phrase for one goal is identical on /diagram and /agents.
- **Stories:** C2
- **Evidence:** pm-tf-home.png, newcomer-blind-tf-agents.png, story-1-b1-home.png

#### Q81. The diagram loads without console errors

- **Pages:** /diagram (all views, all demos)
- **Problem:** Every diagram load logs 'xOffset value … in ShapeConnectionPin constructor greater than shape width'; some log 'ELK failed … reading Sg', after which a fallback layout may explain some overlaps.
- **Change:** Clamp the pin offset to the shape width (an off-by-one at the right edge). Find the input that makes ELK throw and fix it or report the fallback on the page ('simplified layout').
- **Acceptance:** Loading /diagram in Dynamics, Blocks and Process on all six demos, and Into each system, produces no console error or warning from the layout.
- **Stories:** G3, G5
- **Evidence:** newcomer-blind-tf-process.png, sdx-8791-modelling-fit2.png, sre-is-diagram.png

#### Q82. Counts read as words

- **Pages:** side panels, /items Graph, /item/…
- **Problem:** '1 actions', 'last of 2 epic done', '1 re-ping(s)', 'Not held Attempts 0 of 3.' with no separator.
- **Change:** One plural helper for every count; separate the two statements with ' · '.
- **Acceptance:** No page text matches /\b1 (actions|epics|items|loops)\b/, /\(s\)/ or /held Attempts/.
- **Stories:** F2
- **Evidence:** ixd-tf-into-click-stock.png, pm-road-graph.png, ixd-job-item-detail.png

## 4. What to keep

Named by several designers, and to be protected while the changes above are made.

- **The leaf notation of both diagrams.** Dynamics: stocks, double pipes, bow-tie valves, clouds, signed connectors, R and B markers with direction, `<shadow>` variables, and the desired → gap structure where it is drawn (`sdxb-8797-api.png`, `ixdb-sf-dynamics-delivery.png`). Blocks: signed summing junctions, r/e/u/y/d, H on the return, P(s) = 1/s for a stock, relay and dead-band glyphs, C(z) with sampler and hold, MIMO bars with widths, off-page pills (`ceb-is-service-into.png`, `ixdb-sf-blocks-delivery.png`). Monochrome and shape-coded.
- **The evidence panel for a goal.** y with r, u and e on one time axis, off periods shaded, crossings, decisions folded "alike when only their numbers differ", "typically holds again 30s after". An SRE called it a better incident view of one SLO than any dashboard they own (`sreb-job-loop-panel.png`, `infod-tf-loop-click.png`).
- **Loop tracing.** Clicking an R or B marker dims the rest and lights the path, with the "Around the loop" table (`ixd-tf-into-click-loop.png`); hover dims what is not connected; selection is shared between views.
- **The stock panel.** Its causes strip (level with its desired level, inflow and outflow on one axis, replay dashed, projection with its fan), the typeset equation, parameters with units, and "Show them on the Items page" (`sdxb-8796-users.png`, `pmb-sf-users-stock.png`).
- **The controller and process panels' substance.** K ± σ, θ ± σ, residual whiteness, independence from u, the closed-loop data caveat, the refusal to propose a model the data cannot support, the sized step test, the transfer matrix with structural zeros; real MathML (`ceb-is-process-panel.png`, `a11yb-8793-deadband-panel.png`).
- **The honest modelling prose.** "Not exercised by the record: not evidence it is absent", identifiability against time constants, the stock-against-flows balance check. Reword it; do not remove it.
- **The Guide.** Its structure (why, what is, what we control, yours) and above all frame 2, the same loop drawn both ways under "System dynamics draws what is; control draws what we control" (`ceb-guide-1.png`). It is the clearest statement of the product.
- **The software-factory top level.** Two systems with signed links between them: the model every folded home should follow (`story-1-b3-home.png`).
- **The Loops table's columns** (now, bound, error, time off, back in, trend, behaviour): they are the rows the boxes should carry.
- **Items that already read well.** The roadmap's Graph (critical path, what waits, who works on what) and Timeline (`pm-road-graph.png`), image-squeeze's two-state cases chart, the process map with its rework mark, and the item page's Relations.
- **The per-view wording of the side list** (desired and gap in Dynamics, setpoint and error in Blocks). Keep the idea; fix its edges (Q23, Q46, Q62).
- **The shell.** Quiet type, one ink with red only for off, complete dark mode, a visible focus ring on native controls, Escape closing the panel, `prefers-reduced-motion`, landmarks, breadcrumbs, an address per view, "More beyond the edge" in place of shrinking, the time-window menu, the project switcher's counts, the weekly tally per class of action, and the JSON API.

## 5. Left out, and why

- **A text view of the diagram, a hover glossary, a first-visit banner, an Inbox page.** Each is a new surface. The caption (Q02), the view labels (Q03), the keyboard path through the diagram (R9) and the header link (Q43) do the same work inside what exists.
- **Status colour on Blocks' lines.** Blocks stays monochrome; status is a word and a bold e (R4).
- **A confirm dialog on every Approve.** A list that holds still, buttons named for what they answer and a confirmation in place (Q47 to Q49) remove the mis-click without a dialog. Revisit if real approvals show mis-clicks.
- **Prometheus exposition and an Alertmanager channel** (the SRE's "feed the tools that page me"). Right for the intent, but not a page design matter; passed on as a product note.
- **`model-error` as an auxiliary instead of a stock, shadow-variable style, the biflow arrowheads.** Modelling choices in the template, with no cost to a reader today.
- **Shared scales on the Loops sparklines, the system picker's styling, the Guide's first slide.** Taste, or superseded by R1.
