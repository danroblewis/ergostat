# Systems scope the page; items become projections

The owner's design (2026-11-26), written down before it is built. It replaces the routing of commit a3c784cf9 (a
dashboard at `/NAME`, a kind at `/KIND`, a "Kinds" menu, a separate Dashboard editor page). DESIGN.md says what is
built; this says what is to be built and in what order.

The principle is cascading (hierarchical) control: a system is made of subsystems, and what a system is made of is
what its parts depend on, computed from the graph of the model, not declared.

## Words

- **Projection** replaces **kind of item**. A projection is a way of looking at a set of events: a fold of the events
  whose ids it matches, kept as its own table. One id's row is still **an item**, a projection's item
  (`/factory/ticket/1234` is the `ticket` projection's item 1234), so an event's `item` field, `ERGOSTAT_ITEM` and the
  `item_*` views keep their names. "Kind" never means a projection.
- **Defined in.** A projection, a goal, an agent, a stock or a flow is *defined in* one system (its `system:` or its
  file's `defaults:`). That is only where it is written. What it *belongs to* is computed, and it may belong to many
  systems.
- **Ancillary.** A thing a system shows that is not defined in it. Drawn greyer.

## What a system contains (computed)

These are interrelated dynamical systems: they exist to have many connected parts. The interface between two systems is
never declared; it is found in the graph.

- A thing defined in a system is in that system.
- An edge (a flow's from and to, a goal on a stock or flow, a block's reads and writes, a sensor counting a projection,
  a relation or join between projections) whose ends are in two systems is in both, and so are both its ends: a flow
  crossing from `intake` to `delivery` is in both, and the projection it is counted from is in both.
- A subsystem is a component of its parent: what crosses between the parent's subsystems, or between a subsystem and
  the parent, is in the parent too. What stays inside a subsystem (a QA subsystem's own projections, used by nothing
  outside it) is not shown in the parent.
- A parent may give some of its projections to a subsystem (the subsystem's parts use them) and not others; siblings
  may share projections, flows and goals the same way.
- Computed as: everything, then hidden what is internal to another system. `show:` on a system is not part of this:
  it stays only what is most representative of the system (its box's control panel).
- **The default system** is the top level: everything not defined in a system, and whatever crosses between the
  top-level systems. It allows all that a system allows.

`check` and `explain` say, for each system, what it contains, what of that is ancillary and where it came from.

## Events

An event has no system and no projection. A system's Events dashboard shows the events behind what the system
contains (the events its projections fold, and those its sensors read).

## Projections overlap

Several projections may look at the same events, as was always meant: two identical definitions under two names; a
copy of one with one more field; two projections reading different fields of the same events, folding them
differently. Each projection has its own table in the SQLite cache, kept up to date as events come in, and an event is
matched to every projection it fits (today the first match wins: `spec/items.py kind_of`).

## Implied id

A projection named `ticket` defined in `intake`, within `factory`, matches `factory/intake/ticket/*` unless it says
`id:`. One defined at the top level matches `ticket/*`.

## Addresses

`/api` and `/static` are the server's (the remote API moved under `/api/remote/`). Every other address is read one segment at a time from the top
level: each segment is, in that scope, a dashboard, a projection, `goals`, `agents`, or a subsystem.

    /overview                       the default system's Overview
    /diagrams, /goals, /agents, /events
    /factory/overview               factory's Overview (its own, if the model writes one)
    /factory/intake/overview        a subsystem's
    /factory/intake/ticket          the ticket projection's list dashboard, in intake
    /factory/intake/ticket/1234     one of its rows: the projection's show dashboard
    /factory/custom-dashboard       a dashboard the model writes in factory
    /factory/goals/NAME             a goal's show dashboard

A thing is at a scope's address only if that scope contains it. When `ticket`, defined in `intake`, is also in
`factory` (a flow made it cross), both `/factory/intake/ticket/1234` and `/factory/ticket/1234` exist and the deeper
one redirects to the top-most. A link shared before the flow was added still works, and the owner sees that `ticket`
now belongs to `factory` and may want to move its definition there. Nothing has to be refactored for it to work.

A name in a scope goes to one thing by a fixed order (2026-11-27, the owner): a dashboard the model writes there, a
default dashboard, a subsystem, then a projection, goal or agent. The loser is not addressed there (a finding,
`address-shadowed`); its address is the top-most scope where its name is free. Only a thing with no free scope at all
(a top-level `api`, a projection named `events`) is an error. A remote is a system (`systems: NAME: {remote: ...}`),
renamed by renaming the system, and its parts are named by their short names inside it (`/incidents/triage`). A YAML error, or a thing with no address, stops the page: it shows the errors and nothing else.

The server (Python) and the page (TypeScript) each have the same address helpers (resolve an address to its scope and
dashboard, and write the canonical address of a thing), checked against one shared file of cases.

## Dashboards

Every page is a dashboard, and every dashboard is scoped to a system. Some have a further scope: a projection, a goal,
an agent, one row.

- Each system has default dashboards: **Overview**, **Diagrams**, **Goals**, **Agents**, **Events**. A dashboard the
  model writes with one of those names replaces it for that system.
- Projections, goals and agents each have a **list** dashboard and a **show** dashboard (with the row's id as its
  parameter). Ergostat provides them; each may be customized.
- **Editing in place.** There is no Dashboard editor page. Every dashboard can be edited where it is drawn. A hover `+`
  by the nav bar's dashboards makes a new one for the system, saved under a name into the YAML (through propose and
  the owner's Accept, as now). A projection's list and show dashboards are saved with the projection's definition, in
  the file it is defined in; a system's dashboards in its file.

## The shell

- Top left: the **System** tree (systems contain systems).
- The nav bar is the chosen system's: its dashboards, a vertical bar, then one entry per projection it contains. A
  projection with `group: NAME` is in a menu labelled NAME with the others of its group; one without a group is its own
  entry. Ergostat adds no menus of its own.

## Order of work

Each step leaves main working.

1. **The word.** Projection for item: YAML (`projections:`; `items:` read with a finding that it is the old name),
   the CLI, the API, the page, the docs, NOTES.md. Internal Python names later.
2. **Overlapping projections.** Every projection an event fits; a cache table per projection.
3. **The implied id.**
4. **What a system contains.** The analysis, in `check` and `explain`, tested first.
5. **Addresses.** The helpers on both sides, the shared cases, redirects to the top-most address, collisions and YAML
   errors stopping the page. *Built (2026-11-26):* the helpers and cases; the page resolves every address with them
   (Resolve.tsx over GET /api/route-table) and redirects a deeper address to the top-most; every link the page writes is
   canonical (lib/hrefs.ts), and so are the inbox's and why's (spec/routes.py `link`); the old addresses lead to the
   new ones. A block is an agent for addresses (`/agents/NAME`, as the Agents page lists them). Collisions as errors,
   and the page showing only the errors, are a separate change.
6. **Dashboards per system.** The defaults, replacing by name, list and show dashboards for projections, goals and
   agents, and the Events dashboard. *Built (2026-11-26):* each system's Overview (attention, goals, stocks and flows,
   projections), Diagrams, Goals, Agents and Events, their panels scoped by `$system` (every dashboard binds it); a
   model's dashboard of a default's name replaces it in its system; a dashboard is a system's by its file's `defaults:`
   or its own `system:`; saving an edited default writes it into the system's file (else the main file with
   `system:`); a system's Events are those its projections fold and its blocks and agents record (GET
   /api/events?system=). The Record is gone (Events). Left: a goal's show dashboard is its detail (GoalPage), not yet a
   dashboard of panels that can be customized; an agent's list and show are the Agents page and `page: agent` as
   before.
7. **The shell.** The System tree and the nav bar. *Built (2026-11-26):* the System tree top left (indented by
   `within:`, the top level by the model's name), the nav bar the address's system's: its defaults, its dashboards with
   `nav:`, the `+`, a bar, its projections (ancillary ones greyer, with where each is defined; `group:` menus). Left:
   ancillary in a chart's legend.
8. **Editing in place.** The `+`, editing any dashboard, saving with the projection or the system. The Dashboard
   editor page goes.
