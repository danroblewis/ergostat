# The AI agent harness as a control system

Status: design note, 2026-11-17. A discussion between the owner and Claude, written down before
anything is built. It asks what we lose if a single AI agent harness session (Claude Code, which built
ergostat) is replaced by ergostat orchestrating many sessions, and what ergostat must provide so that
nothing essential is lost.

## 1. The premise

ergostat has been built by one long Claude Code session, with the owner talking to it and it
delegating to subagents. That session was the project's control system. The proposal is to develop
ergostat in ergostat: tasks, work, tests and completion run as feedback loops in ergostat itself.

**An AI agent harness is a control system.** It uses a large language model to run sensors (tool
calls), make decisions (thinking and tool calls), manage feedback loops, and do everything else control
systems do. The fantasy behind harnesses is that LLMs can fill the role of control systems adequately.
To replace one, we have to ask what it was doing that made it effective.

Claude Code's design is full of control decisions that Anthropic made to get useful, profitable
behaviour from its models:

- when to reveal CLAUDE.md files;
- how to present skills (a skill's file is shown only when the agent asks for it);
- when to open a sandbox, and how to gate tool calls;
- how to handle periodic wake-ups, `/loop` and goal loops;
- when to compact the context.

## 2. What we already know

**The harness controls the flow of work, including whether to check it.** It receives a task (a message
from the owner), does some of the work, and then *decides* whether to run validation. In this session
it usually did, and that is why the work held up. It also skipped or weakened validation at times: twice
it pushed with failing tests, because a pipe hid the exit code. Nobody uses a harness to *guarantee* work
is done. A harness always lets the agent control the flow, including whether a review step happens at
all.

**Memory is a context window.** System dynamics says stocks accumulate and have memory. A harness's
memory is its context window: a stock with inflows (messages, tool output, files read) and outflows
(compaction, truncation, what the agent chooses not to keep). There are other memories: Claude Code's
memory files, Markdown documents, retrieval-augmented generation (RAG).

**RAG has largely failed.** When context is lost, the contextualisation of information, and with it its
semantic value, is lost too. RAG returns text, not interpretation. Something other than the reasoner (an
embedding search, BM25, Lucene, term matching) decides what is relevant, which replaces the very
judgement we wanted from the LLM. Even with skills, the agent *decides* whether to pull a skill in. In a
harness, most decisions are gated in complex, irregular ways that may not be consistent over time. The
structure of the control system may be governed by the contents of the context window.

**Too much structure changes the behaviour.** Hand an ergostat agent a task id and a description and
tell it to start, without the eighteen hours of slowly built context, and it may behave very differently
from the session it replaces.

## 3. What went wrong before

In Orchestra (the previous attempt), a **Supervisor** agent sat at the heart of the system. It managed
the configuration and talked to purpose-specific agents: a ticket **Coordinator**, a **CI/CD manager**
that fixed merge-pipeline failures. The owner was productive with a chain of sessions: a user-facing
session translating their words for a coordinating session, which managed worker sessions. Attempts to
use it often failed, so it may have been a bad idea.

That arrangement is usually called a *multi-agent system*, not cascade control: hierarchical control
drawn as a linear chain of agents. It was slow and unreliable. Calling the AI "the bottom loop" of
ergostat would just rename the same hierarchy.

**A product-owner agent drifted.** Asked to come up with designs, features, milestones and tickets, its
output declined in importance. It made too many low-value features that cluttered the codebase with
things users would not care about, and replaced earlier design decisions with new ones for very little
value.

In system dynamics terms, that is a missing balancing loop. Features were a flow with no cost attached
and no outcome measured, so the stock of features grew while value didn't. ergostat can supply what was
missing:

- a goal on an outcome that can be measured, not on features shipped;
- the cost of each addition as a stock (complexity, maintenance);
- proposals judged against outcomes, as `ergostat.model-change` items are judged;
- the owner's intent as the setpoint.

## 4. Why an orchestration base that isn't a harness

- **Horizontal scaling.** A harness has a context limit and doesn't scale out. Several sessions that
  don't share a context can.
- **Triggering on events.** Work starts when something happens, not when someone asks.
- **Reliable feedback loops for improvement.** Loops that are consistent over time, unlike agent
  behaviour, keep the work on track. They also help whoever designs them clarify how best to measure the
  goal, by modelling it properly.
- **Harnesses are not good at managing large projects.**

## 5. What a harness does as a control system

Context management aside, a harness does at least the following. Each item gives the evidence from the
session that built ergostat, and what it amounts to in control terms.

1. **It generates its own setpoints.** Vague goals ("make the block diagram not pitiful") become
   concrete sub-goals, re-planned after every observation: plan a few steps, do the first, look,
   re-plan. *Receding-horizon (model predictive) control, with the plan as the reference trajectory.*
   ergostat's goals are fixed numbers; a harness invents and revises its goals as it learns.
2. **It decides when it is done.** Finished, good enough, or another round: "merge now" or "send it
   back". *A discretionary termination condition*, as often wrong by stopping early as by
   over-polishing.
3. **It infers intent, and chooses between asking and acting.** A question costs the owner's time; a
   wrong guess costs rework. *An exploration–exploitation decision about the human*, retuned by feedback
   ("act, don't ask").
4. **It is interruptible, and re-prioritises mid-action.** Messages arrive during work and are folded
   in: drop a task, re-order, answer, resume. *Preemption: the setpoint changes while the actuator moves,
   without inconsistency.*
5. **It gates by risk.** It reads freely, asks before anything outward-facing, and refuses some things.
   Thresholds adapt as permissions are granted. *Interlocks and limiters with adaptive thresholds.*
6. **It recovers from errors by varying, not repeating.** A failing command is diagnosed and tried
   differently: conflict markers resolved, a hung merge checked rather than re-run, a flaky test re-run
   alone to classify it. *Fault tolerance with diagnosis.* Classical retry loops repeat.
7. **It experiments to understand the system.** It re-runs one test, greps before editing, measures
   before designing (the selection-size check before the split view). *System identification of the
   codebase*, with the experiment chosen to answer the current question.
8. **It estimates state before acting, and checks effects after.** `git status` before merging,
   `pgrep` before assuming a run died, reading screenshots before trusting an agent's report. *An
   observer, and closing the loop on its own actions.*
9. **It allocates attention.** Which running thing to look at, when to check on background work, when
   to stay quiet, when to update the owner. *Scheduling under limited attention: interrupts
   (notifications) and heartbeats.*
10. **It delegates, and calibrates trust in what comes back.** It chooses what to hand off, what goes
    in the brief, and how hard to check the result: reliable agents got lighter review, an overreaching
    report got a skeptical look. *Hierarchical control with adaptive gains: verification effort set by
    track record.*
11. **It translates in both directions.** The owner's language becomes technical action, and technical
    state becomes what the owner needs to know, at the right level. *For the owner, the harness is the
    state estimator*: their picture of the project is its reports. The owner is also one of its sensors
    (the frozen session, the bad layouts, the thin Fit page).
12. **It keeps the work coherent.** Each action is checked against conventions, invariants and earlier
    decisions: no new UI, the commit trailer, the port rules, the two perspectives. *Constraint
    satisfaction across time.* This is what the product-owner agent lacked, and why it drifted.
13. **It adapts its own policy from correction.** "Act, don't ask", "justify it" and the pronoun rule
    become memories and change later behaviour. *Adaptive control*, with semantic learning: one
    sentence retunes it, where a numerical controller would need many data points.
14. **It coordinates concurrent work.** A worktree per agent, merging one at a time, telling agents
    what moved on main, keeping two agents out of the same files. *Resource locking and scheduling
    across parallel actuators.*
15. **It filters by value, sometimes badly.** It refuses scope creep, suggests the cheaper path,
    queues instead of building. When this fails, you get low-value feature drift. *A prioritisation
    controller whose objective is a guess at the owner's values.*
16. **It reports truthfully, or doesn't.** The outer loop (the owner) is only as good as the harness's
    honesty. Pushing with failing tests, or overstating what was built, degraded the owner's control of
    the project. *Sensor integrity.*

## 6. What ergostat can take over, and what it can't

| | Functions | What ergostat does |
|---|---|---|
| **Guarantee or measure outright** | 2 stopping (a judge), 5 gating (a policy), 8 state checks (sensors), 9 scheduling and triggers, 14 locks, 16 records instead of reports | Does them *more reliably* than a harness: always, measured, recorded. |
| **Structure, with an LLM inside** | 6 diagnosis, 7 choosing experiments, 10 what goes in a brief, 15 judging value | Gives the LLM the loop, the measure and the gate; the LLM gives the judgement. |
| **Where harnesses are uniquely strong** | 1 setpoints, 3 intent, 4 absorbing interruptions, 11 translation, 12 coherence, 13 learning from correction | All of these ride on semantic context. This is what we would lose. |

## 7. Semantic context management

The most important thing lost when replacing a harness with ergostat is probably **semantic context
management**. Other values people attribute to agents ("deciding", "reasoning", "thinking") are debated
and may be illusions. Semantic context management is real.

Semantic context is not facts; documents hold facts fine. It is the *interpretation* that has
accumulated, continuously re-integrated: every new message is read through all of it. In this project
it includes:

- why a stock is defined by its memory;
- what "no new UI" means;
- that "justify it" means "if you can't, we don't";
- which ideas were rejected, and why;
- why the-job matters (the owner's managers);
- which agents' findings to trust.

Losing it explains the failures of delegation in this session. Every subagent was a fresh context with a
brief: exactly the "task id and description" situation. The briefs grew long because they were
transferring context, and the failures traced to what the brief lost:

- an equations workflow that built fitting machinery when the owner wanted model improvement;
- nobody pointed at SD Lab's existing work;
- an agent inventing "the owner's decision".

The successes came from briefs that carried the owner's words verbatim, and from expert reviewers who
re-read the work cold. **The bottleneck in horizontal scaling is not running more sessions; it is how
context flows between them**, and that is itself a stock-and-flow problem.

Known options, none sufficient alone:

- **Documentation:** retrieval in another form, with RAG's weaknesses.
- **Forking a session at a point** to spawn workers. It works, but there is no way to *merge* sessions
  back.

## 8. Directions

1. **A context holder.** Keep semantic context in a living session, and have ergostat schedule around it.
   One long-lived session's job is to hold the project's context. Workers don't retrieve documents; they
   **ask the holder**, and it answers with full interpretation. That is consultation, not search:
   relevance is decided by a reasoner holding everything. ergostat routes the questions, measures the
   holder's context as a stock (size, compaction, what was lost), and decides when it hands over to a
   successor.
2. **Recombination by integration, not merging.** Sessions can't be merged, but the holder can
   *integrate*: each worker reports back, and the holder reads the report in light of everything. Loss
   happens at the report, so ergostat measures it (did the worker do what the brief meant?), with
   reviews and judges catching drift.
3. **Decisions as an always-loaded record, not a retrievable one.** A small, curated record of decisions,
   *with their reasons and the alternatives rejected*, in the owner's words. It is loaded into every
   session like CLAUDE.md, never searched, and works like the memory index: small enough always to
   include, pointing to detail the agent chooses to open. It is lossy, but it carries interpretation, not
   raw text.
4. **Context transfer as a measured flow.** Every handoff (brief, report, compaction) is a flow of
   context with a loss. ergostat records what each session was given and what it produced, and judges
   score where meaning was lost. Over time, which briefs work becomes measurable.
5. **Value as a balancing loop** (section 3), so proposals of work are judged against outcomes and the
   cost of what they add, with the owner's intent as the setpoint.

**The framing:** ergostat brings consistency, scale, triggers and loops that correct themselves;
harnesses bring semantic context. The design question is how context flows *through* ergostat's
structure, not which of them sits on top. ergostat takes over the mechanical control functions (gates,
judges, scheduling, locks, records), and the semantic ones (goals, intent, coherence, learning from
correction) stay inside sessions that hold context. The interface between them is where the work is.

## 9. Open questions

- Does a context holder scale? It is itself a harness with a context limit, only doing less work.
- Can integration by one reader keep up with many workers?
- Which of a harness's discretionary choices (verify or not, load context or not) correlate with work
  that holds up? Measured, some could become guaranteed.
- How should the owner's corrections (function 13) become part of the always-loaded record without it
  growing past usefulness?
- ergostat-on-ergostat is the place to answer these, because each becomes measurable there.

## Related

- [diagram-options.md](diagram-options.md), [external-systems.md](external-systems.md)
- SPEC §12e: model improvement as a feedback loop, the first loop where ergostat improves itself.
