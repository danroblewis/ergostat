---
name: ergostat-author
description: Use whenever an ergostat project (ergostat.yaml) gets a request for ongoing work, and build it instead of doing it by hand - any request for something to happen as things come in, on a schedule, or until a condition holds ("do X for each new one as it arrives", "tell me if any waits too long", "every morning", "keep Y under N", "remind them until they answer", "when a ticket arrives, do these steps", "watch this API") becomes a small control system made from ergostat's templates (respond-to, re-ping, daily-report, keep-under, steps, collect), even when its script, URL or token is missing; tried on a scratch copy with free stand-ins, and shown to the owner (diagram and diff) before it is turned on.
---

# Add a small control system to an ergostat project

The owner asks for something small. You build it from **templates**: each is a reusable shape (a generic structure
in system dynamics, a library block in control) that expands into ordinary items, stocks, flows, goals and blocks,
grouped as one system per use. You write one `uses:` entry, and scripts only where the template needs a command.

You need the ergostat MCP server (`claude mcp add ergostat -- ergostat -C PROJECT mcp`). Its tools: `templates`,
`add_use`, `scaffold`, `try_use`, `where_drawn`, plus `check` and `explain`.

**A standing request is built, not done.** "Keep the cache under 20 GB", "remind them until they answer", "when a
ticket arrives, do these steps": each is a rule for every time, so measuring, deleting or fetching once now is not
the answer, even to see the state of things. Do not run the work yourself (no deleting files now, no fetching the
ticket now, no drafting the answer now): what you deliver is the system that will do it every time. And do not stop
because something is missing:

- a script the request names that is not there (`bin/help-queue.sh`): `scaffold` it at that very path; it starts
  as a stand-in that runs;
- a URL you cannot reach, a token that is not set, a folder that does not exist: write them into `with:` as the
  request gives them (secrets stay in `$VARIABLES`, read at run time), and try it with `standins: true`;
- an empty repository, no history, no data yet: none of it matters to building the system.

## 1. Pick the shape

| The request says | Template | The goal it holds |
|---|---|---|
| when X arrives, answer / draft / prepare it (within a time) | `respond-to` | the oldest unanswered item's age, under `within` |
| remind them until they answer; chase; nudge again | `re-ping` | no question waits a period without a reminder; at `limit`, a person takes over |
| every morning / weekly / on a schedule, write a report | `daily-report` | every scheduled report written |
| keep Y under a limit; when Y is over, clean / shrink / scale | `keep-under` | the level under `limit` |
| when a ticket (item) of type Z arrives, do these steps in order | `steps` | nothing waits at any step; nothing stays stuck |
| poll this API / command and record what is new | `collect` | none: it is a sensor (the arrival flow's instrument) |

Several shapes compose: two `uses:` entries, or one template's parts named in another's parameters by their full
names (`INSTANCE-PART`, like `stock.questions-waiting`). Items are not tasks: an item is whatever the request is
about (a question, a pull request, a report), and its kind says the states it moves through.

Call `templates` with `name` for the chosen shape: its parameters, defaults, and what stands in for each one left
out. Read its `example`.

## 2. Ask only what is needed

Ask the owner (one short question each, at most two) only for what has no safe default and changes what is built:
the real source when the request names a system you cannot reach, or the number of a limit the request leaves out.
Everything else has a default: take it, and say which you took. Leaving a source or an action out runs the
template on a free stand-in, which is the right start: the system can be seen and tried before any access exists.
If nobody can answer, do not ask: choose, and list your assumptions at the end.

## 3. Write it

- **Name the instance** for what it is, lowercase with hyphens: `review-reminders`, `build-cache`. Its parts are
  named `INSTANCE-...`, and it is a system of that name.
- **Choose the file**: a new file named for the instance, beside the files the project already includes (in
  the-job, `job/INSTANCE.yaml`); `add_use` adds an `include:` when none matches. Put it `within` the system it
  belongs to when there is one (see `explain`).
- **Parameters**: durations are written `30s`, `4h`, `1d`; setpoints are quoted (`"<= 70"`); cron is quoted
  (`"30 8 * * 1-5"`); `steps` is a list (`[triage, {name: fix, run: ./bin/fix.sh}]`). A step an AI agent should
  do is `{name: fix, prompt: prompts/fix.md}`, and its prompt must end by saying `{"event": "KIND.fix-done"}`
  about the item; if it works on code, give `workspace: {repo: ...}` (a worktree per item), and anything outward it
  must do (a push, a pull request) as `actions:` with `gate: approve`, never as a tool. `pool` is how many items a
  step works on at once, `tries` how many attempts before an item is set aside. Only give what the request says or
  needs; leave the rest to the defaults.
- **Scripts**: for each command the template runs against the real world (`command`, `answer`, `measure`, `act`,
  `render`, `ping`, a step's `run`), call `scaffold` with its role and a path (the project's `bin/`, or the
  owner's private scripts folder outside any repository). It runs as it is; fill in its TODO only as far as the
  request says, and keep it **read-only toward work systems**: a reply or reminder is written as a draft into a
  folder (`outbox/`), never sent, unless the owner said it may be. Put the command it returns under `with:`.

Call `add_use` (without `write`). Read `errors` (each points at the `use:` line, or at the parameter that is wrong)
and fix them until `ok` is true. `findings_for_it` says which parameters still run on stand-ins.

## 4. Try it

Call `try_use` with the same arguments (`instance`, `template`, `with`, `file`, `within`) and `seconds: 30`. It
runs a scratch copy and says what moved: items by state, each block's runs and what it moved, goals going off and
holding, sensor failures and block logs. A useful run records items and moves them; a failure says why (a script
that exits non-zero, a parameter that does not parse). Fix and try again. To see the stand-ins alone, add
`standins: true`. A slow parameter (`within: 1d`, `every: 1d`) shows nothing in 30 seconds: trying it with a short
one (`every: 20s`, `poll: 10s`) shows the loop working; write the real one.

## 5. Show the owner, then turn it on

Before anything is written to the project:

1. the **diff** from `add_use`;
2. **where it is drawn**: `where_drawn` with `system: INSTANCE` and `project:` the scratch folder `try_use` gave
   (its text drawing, and the pages: `/diagram?view=dynamics&system=INSTANCE`, the stock-and-flow view, and
   `view=blocks`, the control view);
3. what the trial showed, in two or three sentences, and what still runs on stand-ins;
4. your assumptions.

Ask "turn it on?" Only on yes, call `add_use` with `write: true`, then `check`. When the owner has already said to
turn it on once it checks and runs (a standing approval), that is the yes: write it, then show the same four
things as what was done. Writing it is the owner's own
change: the running ergostat picks it up. Never change the model's other parts to make room for it, and never
call `try_change` or propose model changes for it: that is the modelling subsystem's job.

## When something does not fit

- A request no template covers (a new kind of loop): say so, and build it from the parts in the format
  (`spec`), one goal and the block that serves it, the way the templates are written.
- The owner's own templates: `library:` in the main file names their folders; `templates` lists them beside
  ergostat's own.
