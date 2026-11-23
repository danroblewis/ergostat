# Wave 2: research and design queues (notes)

Area: the owner, "we don't really have any subsystems for research or planning; the knowledge base is very bad, not
even usable by the implementors", and designers own the user stories, keep them possible and obvious for newcomers,
and re-test them. Planned as factory model work (item kinds, blocks, prompts in dev/model, dev/bin, dev/prompts), one
queue per kind of work.

## What exists (read from main)

- **Research is already a kind and a queue**, just a thin one: `research/*` (asked, answered; `ergostat.yaml:256-263`),
  the block `researcher` (pool 1, `dev/model/knowledge.yaml:534-546`), `dev/bin/research.py` (56 lines), asked by
  `ask.py`, the planner (`plan.py:333`) and the pipeline manager (`manage.py:302`). What is wrong with it:
  - the web: its sessions have WebSearch (run by the API) but WebFetch is denied (`agents.py:34-35`) and the egress
    proxy reaches `api.anthropic.com` alone (`factory.toml:74`); no browser at all;
  - evidence: any `<report>` is accepted; its `## Sources` lines are stored, never checked (`research.py:48`);
  - nobody reads an answer twice: the planner gets the report once (`plan.py:312`), the implementor and reviewer
    never (`knowledge.py:36-39`, no research in MORE); the proposal says so (`knowledge-graph.md:19`).
- **The knowledge base** is three markdown files plus the record's applied lessons. `finding` entries are synced but
  "not yet carried in briefs" (`dev/knowledge/README.md:24`). The knowledge queue (lesson items, `lesson-apply`, no
  gaps) is merged and works.
- **Stories** live outside the repository (the design folder's stories.md, 46 stories A1-H6). Two filed gaps walk them
  *as gaps* (`stories-rerun-after-owner-list`, `stories-rerun-after-redesigns`: documentation-only gaps for an
  implementor), which is the wrong queue by the owner's rule. `stories-reflect-owner-decisions` (ready) brings them
  into `docs/roadmap/stories.md`: the story queue depends on it.

## What the implementor (or designer) needs in its container to run a browser against a demo

Most is there already:
- **Chromium and Playwright 1.63.0**: in the dev image (`Dockerfile`: `uvx --from playwright==1.63.0 playwright install
  --with-deps chromium`, `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`, the uv cache offline); proven by
  `tests/test_agents.py::test_implementor_environment_has_a_browser`.
- **ergostat itself**: editable from /work with the venv at /opt/venv, so it runs from a read-only clone too.
- **the demos**: `examples/<demo>/` in the clone; they run offline (`demo_check.py` OFFLINE: `TF_OFFLINE=1` for
  ticket-factory) and need no network, so the internal network is fine.

Missing, and filed below:
1. an allowlisted command to start one demo from a fresh copy in /tmp on its port, wait until its web answers, and stop
   it (`scripts/demo_up.py`; sessions may not run `ergostat run` freely);
2. an allowlisted walker that drives Chromium through a steps file and writes screenshots and the visible text
   (`scripts/walk.py`, the design review's browse.py brought in and tested);
3. a writable folder for the pictures, mounted per session (`/shots`), copied out to `run/stories/<walk>/`, which the
   session reads back with Read (images) to judge what it saw;
4. NO_PROXY for localhost (run_args sets `NO_PROXY=` empty and HTTPS_PROXY to the egress: the walker launches
   Chromium with no proxy for 127.0.0.1, and the open-web proxy only for the researcher);
5. more CPU than a session's 1.5 (`factory.toml:78`): an engine plus Chromium on 1.5 CPUs makes "Open shows something
   within one second" stories fail for the machine's sake. A `designer_cpus` (3) for the roles that run a demo.

## The gaps (10), and their graph

All prefixed `research-design-queues-`:

```
walk-and-demo-scripts ─┬─> sessions-see-a-demo ──┬─> designer-walks-stories ─> walk-findings-as-gaps
                       └─> research-open-web     │
stories-reflect-owner-decisions (filed) ─> story-kind-and-sync ─┬─> stories-due-after-merges
                                                                └─> designer-walks-stories
research-sources-checked ─> findings-applied-carried
research-in-gap-briefs (alone)
```

Wide: five start at once (walk-and-demo-scripts, research-sources-checked, research-in-gap-briefs, story-kind-and-sync
once its filed dependency lands, and nothing else blocks them). Longest chain four.

Cost guard: 46 stories at a $2 session is $92, over the $40 day. So stories are made due a few at a time
(`[design] due_per_day`, default 4), failing ones first, and the designer block waits on `goal.ai-budget.off`.

## What to do with the parked kb-* gaps

The coordinator parked them: "knowledge-base work does not belong in the gap queue or with its workers; it waits for
its own item kind and queue". My reading, for the coordinator:

- **The queue they wait for is the knowledge queue** (lesson items, `lesson-apply`, the gate `knowledge-change`). It
  carries *content*. `findings-applied-carried` (below) widens it from review lessons to findings, with research
  answers as the first source, so the knowledge base starts holding something implementors use.
- **kb-proposals**: resume after `findings-applied-carried`, re-defined: its "approval makes a gap"
  (`knowledge-<name>`, then `facts.md`) is exactly what the owner refused; facts become `finding` lesson items applied
  by lesson-apply, and its "research produces knowledge" bullet is dropped (done here). Then it depends on that gap.
- **kb-mcp, kb-parts, kb-writeback, kb-planner-reads**: keep parked. They are retrieval at scale; resume when briefs
  start dropping knowledge (`knowledge_dropped` non-empty on, say, a quarter of first briefs), a measured trigger.
- **kb-usage-lift, kb-curation-flags, kb-curator, kb-contradictions**: keep parked until there are about 20 active
  findings; they are the knowledge queue's upkeep and have nothing to judge before.
- **kb-why-eval, kb-reflection**: keep parked (no evidence yet that retrieval limits explain).
- **knowledge-diagnose-from-the-current-record-not-an, knowledge-test-the-real-path-and-what-the-user** (lessons filed as
  gaps, parked): close; add them as lessons with `lesson.py add` (the knowledge queue), never as gaps.

## Filed gaps this set replaces

- `stories-rerun-after-owner-list` and `stories-rerun-after-redesigns`: close once `designer-walks-stories` and
  `walk-findings-as-gaps` merge; their walk is the story queue's first sweep (make all stories due once by hand,
  `stories.py due --all`). Until then they stay as they are.
- `keyboard-story-in-browser-tests` stays: a regression test is the gap queue's.

## Questions for the owner (one sentence each)

- What share of the stories must be possible and obvious for the goal to hold (I set 0.8, an estimate)?
- May the researcher reach any public HTTPS host (private addresses refused), or only a list?
