# ergostat: blind review by an SRE

Reviewer persona: an SRE who works from dashboards, alerts and runbooks. My questions were what this adds and what I do when something is off. I used only the running demos: ticket-factory :8791, software-factory :8796, big :8797 and image-squeeze :8793. Desktop is 1440x900. I also checked phone width (390x844) and dark mode. Screenshots are in `shots/`, prefixed `sre-`.

## What I think it is (before judging)

ergostat is a control-loop and system-dynamics console for automated work pipelines. The pipelines are mostly AI agents and scripts that move "items" (Jira tickets, PRs, images, requests) through states.

- It models the pipeline as stocks and flows, for example `located`, `pr-open` and `review-asked`.
- It declares feedback **loops**. Each loop has a setpoint, for example `located ≤ 0`, and a controller/valve that acts to hold it.
- It reports each loop as **holding**, **off** or **unknown**.
- It records every event in a **Record**, which is an event log.
- It lists the **Agents**: persons, AI agents, programs and rules, with their runs, CPU and memory.
- It tracks **Items** through their state machines with leases and attempts.
- It gates outward actions such as `git push`, `pr-merge` and `jira-transition` behind human Approve/Deny.

The audience appears to be the operator or owner of an "AI software factory". That person supervises automated workers, approves risky actions and tunes the loops. The design leans heavily on control-theory and SD vocabulary: "u → y", "dead time", "Harris index", "integrator", "valve", "setpoint". **How sure am I:** fairly sure about the what, about 70%. I am less sure that someone like me is the intended user. It reads as a tool for the person who builds the factory more than for whoever is on call for it.

**What it adds for an SRE:** it frames SLO-like conditions as loops with an explicit corrective actor. That framing is genuinely useful: "this queue should be ≤ 0, and *this* agent is supposed to drain it, and its valve never opened". The per-loop panel is the best thing here. It shows y/u/e charts, the last decision, sensor/controller/valve parts and the crossing history. The gaps sit at the edges, in alerting, linking, trust in the numbers, and runbook-style guidance.

## Findings, worst first

### Blockers

1. **`/` (Diagram, Needs attention): Approve/Deny buttons sit in a live list that keeps reordering.** On every refresh, items in the "Needs attention" sidebar appear, vanish and swap places. These include action approvals for `git push --force-with-lease`, `pr-merge` and `jira-transition`. Between two screenshots seconds apart, the action next to the first Approve button changed from a `jira-transition` to a `pr-comment`, and later to a `git-push` and a `pr-merge`. *Why it matters:* this is a production-change gate. A list that moves under the cursor will eventually get a mis-click approval of the wrong action. *Fix:* freeze the list while the pointer is over it, or require selecting a row before acting. Show the full command in a confirm step and key the buttons to the action id. Screens: `shots/sre-tf-home.png`, `shots/sre-tf-attn-click.png`, `shots/sre-tf-diagram-export.png`, `shots/sre-tf-process.png`.

2. **Every demo: the `requests-handled` loop is "off" ~94–99% of the time (36, 37, 81, 164 unanswered), and nothing changes.** The loop panel says "Its valve did not open in the 4m recorded". It also says "Last decision 4m ago: act: fixer" and "Moves requests-answered 2.79/h". It sits at the top of Needs attention in every demo. *Why it matters:* an alert that is always firing teaches people to ignore the whole panel, which is classic alert fatigue. Either it is a real broken loop, in which case something should escalate, or it is a demo artifact that should not be red. A controller that "acts" while its valve "never opened" is also a contradiction I cannot debug from the UI. *Fix:* when a loop has been off for most of the record and its actuator never fires, show it as *broken actuator* with escalation. Otherwise allow ack/silence with an owner and an expiry. Screens: `shots/sre-tf-loops-click.png`, `shots/sre-tf-evidence.png`, `shots/sre-big-loops.png`.

### Major

3. **No alerting, no machine-readable outputs, no deep links.** `/metrics`, `/api`, `/healthz` and `/alerts` all return 404. The "N loops off" badge in the header is a plain `<span>` and goes nowhere. The Record filter and the time-window choice do not change the URL. Loop rows on `/loops` open a side panel but have no URL of their own. *Why it matters:* I cannot page on a loop going off or scrape loop state into Prometheus/Grafana. I also cannot paste a link to "this loop, this window, these events" into an incident channel. That is most of what I would come here for. *Fix:* give each loop, filter and window a stable URL. Make the header badge link to `/loops?status=off`. Expose loop status as metrics or webhooks. Screens: `shots/sre-tf-record-filter.png`, `shots/sre-tf-loops-7d.png`.

4. **Brief excursions show as "0% time off" and the loop's behaviour label changes from refresh to refresh.** In big, `billing-q1-low` shows "Time off 0% of the 7m recorded". Its crossing list shows **21** off/holding crossings and a y spike to 22 against a setpoint of ≤ 20. The Behaviour column changed between refreshes from "oscillates, 4.05 s" to "within its bound", and `api-q1-low` changed the other way. *Why it matters:* a loop that crosses its bound every ~30 seconds is flapping. "0%" hides it, and a label that changes on every refresh cannot be trusted or alerted on. *Fix:* report crossing count and flap rate next to time-off, and smooth the behaviour classification with hysteresis. Screen: `shots/sre-big-loop-osc.png`.

5. **The flow figures cannot be trusted: rates keep climbing with nothing in flight, and the stock accounting does not add up.** On ticket-factory all 8 tickets reached `done`. Meanwhile the diagram showed `address` climbing 1.98 → 6.11 tickets/min and `repinging` climbing 18 → 43 pings/h. Needs attention says "stock review-asked changed 0, the known flows explain 142: −142 unexplained" and "stock pr-open … explain −71: 71 unexplained". `model-error` rose 0.27 → 0.99 over ten minutes. Check lists 13 flows whose "equation fits its record worse than holding it at its mean". *Why it matters:* if the tool's own figures drift without explanation, I cannot use it as a source of truth during an incident. *Fix:* label exactly what each number on the diagram is (instantaneous rate, window average or cumulative) and its window. Treat a large "unexplained" stock change as a model/instrumentation fault, separate from operational alerts. Screens: `shots/sre-tf-home.png`, `shots/sre-tf-hover.png`, `shots/sre-tf-dark-diagram.png`, `shots/sre-tf-check.png`.

6. **`/diagram` overview on big/software-factory: the system boxes show no health.** Big has six systems and five loops were off (web-q2 at 15 against ≤ 5, build-q3, support-q2). Every module box still looks identical: a black outline and "4 feedback loops inside". *Why it matters:* the first screen of a monitoring tool should answer "which part is unhealthy?" at a glance. Here I have to read the sidebar text and map names back to boxes myself. *Fix:* colour or badge each module by the worst loop inside it (off/unknown count). Screens: `shots/sre-big-diagram.png`, `shots/sre-big-process-fit.png` (5 loops off in the sidebar, nothing on the canvas).

7. **`/diagram` Process view on big is an empty canvas.** The sidebar says "5233 events in the window", then "Kinds 0 — No kinds of item here". The canvas stays blank after waiting and pressing Fit, with no message on the canvas itself. *Why it matters:* a blank chart reads as "the page is broken". *Fix:* put an empty-state message on the canvas, or hide the Process view when there are no item kinds. Screens: `shots/sre-big-process.png`, `shots/sre-big-process-fit.png`.

8. **Needs attention on big is flooded by modelling requests.** Around 24 near-identical items read "request/… modelling holds no-unit on stock.api-q0 … nothing says its unit (no stock it joins has one, and it counts no one kind)". Each has only a Deny button (no Approve) and they push the one real loop alert out of view. *Why it matters:* this is a model-housekeeping queue, not an operational alert, and mixing the two buries real problems. *Fix:* group identical requests into one row with a count, give modelling its own lane, and keep operational loops on top. Screens: `shots/sre-big-diagram.png`, `shots/sre-big-blocks.png`.

9. **Agents page: failed or missed runs are not called out.** In big, `improver` shows "0 · never ran · every 3m" after more than 5 minutes up, in grey text like everything else. `judge` shows "not run here · every 30s". There is no failure/exit column or error count, and cost/tokens are "–" everywhere. *Why it matters:* a scheduled job that never ran is exactly the kind of silent failure I would want flagged. *Fix:* add last exit/failure count and highlight "missed schedule". Screen: `shots/sre-big-agents.png`.

10. **`/agents` headline counts contradict the section headings.** The header strip says "2 person → 4 ai → 13 program → 16 rule". The sections below say "0 person", "1 ai", "4 program", "5 rule", and those sections list 2, 4, 13 and 16 rows. Big shows "32 program" above a "4 program" heading. *Why it matters:* contradicting counts on the first table make me distrust every other number. Screens: `shots/sre-tf-agents.png`, `shots/sre-big-agents.png`.

11. **Model page "process / controller / scope" links do nothing.** They are `href="#"` links. Clicking "process" leaves the page text and URL unchanged. *Fix:* make them open the panel they name, or remove them. Screen: `shots/sre-tf-model-process2.png`.

12. **No runbook guidance in plain operational terms.** The loop panel's text includes "no one process", "its dead time: a step of u, or a step test", "a ceiling or a floor is not held at zero error: judged by its violations instead" and "What if it held at  (" with a blank value. The Suggestions give real advice ("Hold picked-located back while located-worked is off"), but its "why" is "said after 10m of record". *Why it matters:* when a loop is off I need "probable cause → who owns it → what to do / where to click", not control-theory diagnostics. *Fix:* add an "If this is off" block per loop: owner/agent, the last action taken, a link to the agent's recent runs, and the declared remedy. Fill in or hide the blank "What if it held at" value. Screens: `shots/sre-big-loop-osc.png`, `shots/sre-tf-model.png`.

### Minor

13. **The header "N loops off" changes every few seconds and disagrees with other counts.** It read 3, 4, 5, 6, 2 within minutes on ticket-factory. The demo switcher at the same time said "(8 off, 1 unknown)" and then "(7 off)" for image-squeeze. Needs attention said 9, 14, 15, 16 or 17. There is no "since" and no trend. *Fix:* debounce, and show "N off for > X s" as the alerting number. Screens: `shots/sre-tf-loops.png`, `shots/sre-tf-record.png`, `shots/sre-tf-items.png`.

14. **Module loop counts disagree.** The factory box says "36 feedback loops inside" and its side panel says "47 feedback loops inside". The big `api` box says 4 and its panel says 15. Both module descriptions are a bare "…". Screens: `shots/sre-tf-flow-click.png`, `shots/sre-big-api-click.png`.

15. **Opening a module overflows the viewport and does not re-fit.** Factory "Open" pushes the content under the sidebar, with "More beyond the edge" showing. On big, opening a module scrolls the canvas so a module title sits under the toolbar. Screens: `shots/sre-tf-factory-open.png`, `shots/sre-big-api-open.png`.

16. **The Blocks view has overlapping wire labels.** "2 3 2" and "2/3" collide at the review block, and wires run on top of each other. Screen: `shots/sre-tf-blocks.png`.

17. **The Items stacked state chart uses only grey shades for 16 states.** Neither theme lets you tell which band is which, and done/merged/stopped/dead are indistinguishable. Screens: `shots/sre-tf-items.png`, `shots/sre-tf-dark-items.png`.

18. **Record timestamps have no date or timezone (`03:25:02`), and the data column is truncated JSON.** The item page uses a different format (`11/22/2026, 03:24:02`). For incident timelines I need one consistent format with an explicit timezone, plus an expandable payload. Screens: `shots/sre-tf-record.png`, `shots/sre-tf-item.png`.

19. **Phone width: the Loops table hides now/setpoint/error behind a horizontal scroll, and the nav is clipped ("Mode…").** On a phone, the numbers that matter when paged are off-screen, and only name/status/holds show. *Fix:* on narrow screens show loop, status, now vs setpoint and time off as a card. Screens: `shots/sre-tf-phone-loops.png`, `shots/sre-tf-phone-diagram.png`.

20. **Items table is cut off on the right at 1440px.** The "attempts" column shows "0/" and later columns are hidden, with no visible scroll affordance. Screen: `shots/sre-tf-items.png`.

21. **Check page tail is a single run-on paragraph of "no description" warnings,** in small grey text and hard to scan. Screen: `shots/sre-tf-check.png`.

22. **Console errors on image-squeeze `/diagram`.** The console logs `xOffset value (408.4) in ShapeConnectionPin constructor greater than shape width (408.4)` three times. Screen: `shots/sre-is-diagram.png`.

### Polish

23. **The Guide is a generic SD tutorial** ("You control the knob. You want the stock." with ad-spend/customers) and is not tied to the system on screen. A "how to read this system's loops when one is off" page would be more useful to me. Screen: `shots/sre-tf-guide.png`.
24. **Error sign convention (`r − y`) gives negative errors for "too high" queues** (−36). SREs usually read "over by 36". The Blocks view already says "(off by 36)", so the wording is inconsistent between views. Screens: `shots/sre-tf-loops.png`, `shots/sre-tf-blocks.png`.
25. **The diagram has no hover tooltips on flows or values.** Hovering `repinging` only outlines the module. Screen: `shots/sre-tf-hover.png`.
26. **The person-approve input placeholder is truncated** ("how ma"), and the alert text references a CLI (`ergostat actions`) that a web user may not have. Screen: `shots/sre-tf-home.png`.
27. **Dark mode is generally clean.** Red and amber stay legible. No issue found beyond the grey-only state chart (17). Screens: `shots/sre-tf-dark-diagram.png`, `shots/sre-big-phone-dark-diagram.png`.

## Bottom line

The loop-as-SLO-with-an-owner idea and the per-loop panel add something my dashboards do not have. Several things stop me from relying on it during an incident:

- an alert that is always red;
- counts that contradict each other;
- rates that move with nothing in flight;
- an approval gate in a list that reorders itself;
- no alert outputs or shareable links.
