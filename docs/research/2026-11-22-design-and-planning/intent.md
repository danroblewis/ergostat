# What ergostat is meant to be (the owner's intent)

Read this only after your first, unbriefed walk.

## The idea

ergostat models a running system (a team, a software factory, a platform) as **feedback loops**: what exists and how much of it (stocks), how it moves (flows), what is wanted (goals with setpoints), what measures it (sensors), and what acts (blocks: AI agents, scripts, people, external controllers). It reads the real system's events and metrics, runs its own agents and scripts when a goal is off, and lets people see why a loop is off and what would fix it.

It sits **on top of** existing tools (monitoring, alerting, ticketing, autoscalers). It does not replace them. It holds what none of them hold: the model relating them, its structure and equations. The owner's aim is to move operations work from "monitoring and observability" to "dynamics and controls".

Where the owner expects its value: explaining systems coherently, in design and proposal docs; projections for capacity and cost; predicting failures and risky areas; proposals that remove redundant or conflicting services; the long-term health of products; clearer expectations for product managers; and, run on servers, joining existing control systems as another controller.

The audiences: engineers and SREs (what they control and what they must do), and product managers and others (what really exists and what they sell). Expect doubt in three steps: is it useful at all, will people use it, will it have meaningful impact.

## Design decisions already made

1. **No new pages, panels or views.** The owner: "The easiest thing to do, which we must always avoid, is to add more junk, add more pages, add more panels... We want the simplest UI possible, and that will probably mean the diagram; the diagrams can represent almost everything we want." Show things through what exists: the diagrams, the system boxes and their exposed parts, and the Items tab. Prefer modelling an idea (a measure as a stock, an example as an item) over new UI for it. A "control panel" is the diagram with everything else folded away. You may propose changing, merging or removing pages; proposing a new one needs an exceptional case.
2. **Two perspectives, two diagrams, each true to its discipline.**
   - **Blocks (control theory):** what is controlled. Control loops, cascades and hierarchies. Monochrome, few shapes, a function in every block (C(s), P, H with subscripts), summing junctions, r/e/u/y/d, the definition on click; drilling into a subsystem belongs here.
   - **Dynamics (system dynamics):** what is. Stocks, flows, auxiliaries, connectors with link polarity, R/B loops, per Sterman. No sensors or controller blocks drawn here; a goal is a goal-seeking auxiliary.
   - The test: each diagram "instantly clear and obvious" to an expert of its discipline, looking like what they read everywhere else. One model underneath; never mix the notations.
3. **Only recognised diagram types.** No invented diagrams. The Wiring view is to be replaced because it is not a standard diagram. New diagram types wait until user flows are worked out.
4. **Items are not tickets.** An item is a fold of events (a gap, a session, a lesson); some kinds complete, many live forever.
5. **Systems are namespaced.** A part that belongs to a system has the system's name prepended; where the system is known, it may be shown by its short name.
6. **Large systems matter.** The owner's own development factory runs as an ergostat model of hundreds of parts, and the UI has real problems at that size (see the `big` and `software-factory` demos).
7. **Read-only for people, except a few gated actions.** People approve or deny what agents ask for (the Inbox); they do not edit configuration through the page.

## Where to read more (in DESIGN/ergostat)

`README.md`, `docs/WHY.md`, `docs/CONCEPTS.md`, `docs/QUICKSTART.md`, `docs/DESIGN.md`, `docs/DISCIPLINES.md`, `docs/DECISIONS.md`, `docs/layout-rules.md`, `docs/vocabulary.md`, `docs/proposals/diagram-options.md`, each demo's `README.md` under `DESIGN/demos/`. `docs/SPEC.md` is the full specification (long; search it).
