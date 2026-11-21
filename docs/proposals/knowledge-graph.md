# The knowledge graph, and planning in proportion to the gap

Status: proposal, 2026-11-20. Nothing here is built. It answers the owner's words of the same day: "some gaps are
small, some features are small, some are big, some are very big... The amount of effort it takes to review a plan,
and the amount of planning we want, depends on how big a gap is. I would hope that most planning has already been
done, in the knowledge base. I haven't seen the knowledge base do much... The knowledge base should contain some sort
of structured data, a directed cyclic graph, with a querying interface, and maybe MCP tools for the AI agents."

## Where we are

**The knowledge base is three markdown files.** `dev/knowledge/` holds about 177 lines: the house rules, 13 review
lessons and 9 decisions. `dev/bin/knowledge.py` splits them into entries by regex (`rules-process`, `lesson-3`,
`decision-<slug>`). `knowledge.block()` pastes them into every brief by priority within `[knowledge] chars`, followed
by related gaps, past findings on the files the gap touches, and the module map. `knowledge-sync` mirrors each entry
as an item `knowledge/<id>` (active, retired) and records how many briefs carried it. The librarian
(`dev/bin/librarian.py`) proposes lessons from review findings. Each approved proposal becomes a gap whose definition
is the exact edit. That is a whole build-review-merge cycle for one paragraph.

**Research leaves no trace in what we know.** `dev/bin/research.py` writes reports to `run/research/`, and three exist.
A planner waiting on a question is given the report once and nobody reads it again. The reports have no relations,
nothing measures them and they never go stale.

**Planning is uniform and costs too much.** `dev/bin/plan.py` plans every open gap with Opus, and every plan then gets
a plan review. A planning session costs about as much as the build. Plans are over-specified: about 16 acceptance
tests on average and a median budget of 270 lines (`run/plans/act-risk-gating.md` is typical: it pins every reason
string). The split (`gaps-split`, the join on `parent`, `plan.py splits`) exists, but no split gap's children have
merged yet. That means splitting is **not verified**.

**What the core already has, and this proposal reuses:**

| Need | Already in ergostat |
|---|---|
| Nodes with history and provenance | items: every field change kept with the event that made it (SPEC §5a *History*) |
| Typed directed edges, both ways, cycles allowed | `relations:` on a kind, the item index's `links` table indexed both ways (`spec/itemindex.py`); cycles matter only for `precedence: true` relations (`precedence.relation_cycles`) |
| Neighbourhood over relations | `precedence.build` reaches `HOPS` links out for the Graph view (`GET /api/items-graph`) |
| Owner-confirmed decisions | the built-in kind `ergostat.decision` (proposed, confirmed, superseded) and `ergostat context decisions` |
| A brief as a measured recipe | contexts (SPEC §12j): each use is recorded with the hash of what was rendered, and the work's outcome is folded onto it |
| Judging "done as meant" | the intent judge (SPEC §12i) |
| Agent tools | `ergostat/mcp.py` (stdio JSON-RPC; `explain`, `findings`, `status`, `items`, `context`, ...) |
| What a session read | session items fold `tool_calls` and `tool_results` from the transcript (`dev/bin/sessions.py`) |
| Proposals held for a person | the gated action `knowledge-change` and the inbox |

Nothing new is needed for storage. We need item kinds, a few relation names, one core index (full text), a query
module, and the loops that keep the graph honest.

## 1. The graph is items and relations

**One kind for entries.** We widen the existing kind `knowledge` instead of adding several. Each entry is
`knowledge/<type>/<slug>`, with a `type` field:

| `type` | What it is | Example |
|---|---|---|
| `component` | a part of the intended architecture | "the item index", "the merge queue" |
| `rule` | an architecture or house rule that must hold | "one system, one model"; "definition first" |
| `lesson` | a class of mistake reviews find, with its check | today's `lesson-3` |
| `finding` | something learned: a research answer, a planner's discovery, what a simplification removed and why | "the join reads O(children) per move" |
| `question` | something not known yet | "does splitting produce mergeable children?" |
| `source` | where knowledge came from: a SPEC section, a doc, a research report, a review | `source/spec-5a` |

Decisions stay in `ergostat.decision`, which already has the owner's confirm and supersede flow. Open research
questions stay `research` items at `asked`. Each answer becomes one or more `finding` entries that cite the research
item. Code and the model are entries too, but they are **referents**, kept by a collector (below):
`part/<stock|flow|auxiliary|goal|block|system>.<name>` and `file/<path>`.

**States:** `proposed` (an agent or a program said it; it is usable but marked unconfirmed), `active`, `stale` (a
referent changed under it) and `retired` (with a reason, kept in the record). `knowledge.found` / `.changed` /
`.retired` from today's sync remain. New events are `.proposed`, `.confirmed`, `.staled`, `.refreshed` and `.used`.

**Relations** are declared on the kind in `ergostat.yaml`. Every one is `precedence: false`, so a cycle (A explains B,
B is evidence for A) is allowed and never shows up as a scheduling finding. Watch the names: `depends_on`, `after` and
`blocked_by` default to precedence (SPEC §5a), and `parent` defaults to a group.

```yaml
  knowledge:
    id: knowledge/*
    states: [proposed, active, stale, retired]
    search: [title, text]                      # new, generic: full-text indexed (§2)
    relations:
      part_of:      {kind: [knowledge], precedence: false, inverse: has_part}
      uses:         {kind: [knowledge, part, file], precedence: false, inverse: used_by}   # "depends on", not precedence
      implements:   {kind: [knowledge], precedence: false, inverse: implemented_by}   # a rule or finding made real by a component
      supersedes:   {kind: [knowledge], precedence: false, inverse: superseded_by}
      contradicts:  {kind: [knowledge, ergostat.decision], precedence: false, inverse: contradicted_by}
      evidence_for: {kind: [knowledge, ergostat.decision], precedence: false, inverse: supported_by}
      explains:     {kind: [knowledge, part], precedence: false, inverse: explained_by}
      about:        {kind: [part, file, gap, ergostat.decision], precedence: false, inverse: known}
      cites:        {kind: [knowledge, research, review, session], precedence: false, inverse: cited_by}
```

**Provenance and confidence.** Each entry has `by` (`file:dev/knowledge/...`, `session/<id>`, `program/<name>`,
`coordinator`), `confidence` (0 to 1, set by whoever proposed it and adjusted by the curator), `origin` (`seeded`,
`authored`, `learned`) and `checked_at`. The provenance of each **edge** is already recorded: the field history keeps,
per path, the event that added or removed the link. An edge that needs its own confidence (an inferred `about`)
records it in `link_confidence: {"about:file/dev/bin/queue.py": 0.6}`. No change to how relations fold.

**Referents stay current.** A collector, `parts-sync`, a program run on each switch of the instance, keeps one item
per model part (`part/stock.gaps-ready`, with its spec's hash and its file and line) and one per tracked file under
`ergostat/`, `dev/`, `scripts/` and `docs/` (`file/dev/bin/queue.py`, with its blob sha on main). It works like
`knowledge-sync`: it says only what changed, and a part or file that disappears is retired. When an entry is
written, its `about` targets' hashes are recorded in `anchors: {"file/dev/bin/queue.py": "<sha>"}`. When a referent's
hash moves past the anchor, the curator moves the entry to `stale` (`knowledge.staled`, naming which referent). It
returns to `active` only when someone refreshes it (re-reads it and confirms or edits it), which records new anchors.
A one-line whitespace change to a file does not stale anything: the anchor for a `.py` file hashes the AST dump, not
the blob. That costs a few thousand items, well within the item index (the Items page caps what it draws, not what it
keeps).

**Shown on existing pages only.** The Items page's Graph view draws `kinds=knowledge,part,file` (by kind, frames
per `type`). An entry's item page already lists its relations both ways. A part's item page lists what is `known`
about it (the inverse). The Dynamics and Blocks panels already link a part to items; they link to `part/<name>`.
No new page or panel.

## 2. Querying

**One query module, generic over items.** `ergostat/graphquery.py` uses only the stdlib and sqlite, reads the item
index, and knows nothing about knowledge. It offers:

| Query | Meaning | Built from |
|---|---|---|
| `near ID [--hops 2] [--rel about,explains]` | the neighbourhood, both directions | `links` (`links_rid`, `links_dst`), the BFS `precedence.build` already does |
| `path A B [--most 5]` | the shortest typed paths between two items | BFS over the same rows |
| `about REF` | everything about a file, a part, a gap or a **loop** (its members, from `spec/causal.py`), ranked by confidence and recency, stale entries marked | inverse `about`, plus `about` on the parent folder or system |
| `search TEXT [--kind K] [--state S]` | full text | **new:** an FTS5 table `texts(rid, field, body)` in the item index, filled by the fold for the fields a kind lists under `search:` |
| `get ID` | the entry, its relations and its history | `ergostat item ID --history` |

**CLI:** `ergostat items --near ID`, `--path A B`, `--about REF`, `--search TEXT` (beside today's filters).
**API:** the same as query parameters on `GET /api/items`. **Brief assembly:** `knowledge.block()` calls `about` for
the files and parts the gap names, instead of regex over markdown.

**MCP tools for agents.** `ergostat/mcp.py` gets five read tools: `kb_search`, `kb_about`, `kb_near`, `kb_path` and
`kb_get`, all thin calls into `graphquery`. Inside a factory session these tools have to reach data without the
network, and there are two ways to do that:

- *Served over the egress proxy:* this means letting the sandbox open a route to the host's ergostat API. That API
  has write endpoints. The proxy also only tunnels named TLS hosts on 443 (`dev/agent/egress.py`), so it would need a
  new listener and auth. It weakens the one property the containers exist for.
- *A read-only snapshot mounted:* **this is the choice.** Before a session starts, `agents.py` exports the graph
  (items of `knowledge`, `part`, `file`, `research` and `ergostat.decision`, their links and the FTS table) into
  `run/kb/<hash>.db`. It mounts the file at `/kb/kb.db:ro` and the installed version's code
  (`~/ergostat-live/current`) at `/ergostat:ro`. It adds `--mcp-config` with one stdio server, `python3 -m
  ergostat mcp --snapshot /kb/kb.db --tools kb`, run from `/ergostat`. The session's own `/work` is code under
  change and never runs the server. `--strict-mcp-config` is already passed, and the role's `--allowedTools` gains
  `mcp__ergostat__kb_*`. The image already has Python and the locked dependencies offline.

A snapshot is out of date by at most one session, which runs two hours at most. It is also reproducible: the
snapshot's hash goes on the brief's recorded context, so attribution knows exactly what the session could see.
Snapshots are kept by hash and only the last few are kept, as the module map does today.

**Writes do not go through MCP.** A session proposes knowledge the way a planner proposes research today, with a tag
in its result:

```
<knowledge type="finding" about="file/dev/bin/queue.py, part/block.merge-queue" confidence="0.7">
A queue failure on a gap whose suite passed alone is triaged as a flake before any fix round.
</knowledge>
```

The host program (`plan.py`, `research.py`, `implement.py`, `review.py`) records each tag as `knowledge.proposed`,
with `by: session/<id>`, the gap, the anchors, and at most five tags per session. They are proposals and the curator
decides what happens to them (§3).

## 3. What goes in, and the loop that keeps it good

**Seeded once by programs, then confirmed:**

- *The intended architecture.* One `component` entry per SPEC section that names a mechanism, and one per package in
  the module map (`knowledge.module_map` exists). Each `cites` its `source/spec-<n>` and is `about` the files its
  section names (`DOC`/`FILES` regexes exist in `brief.py` and `knowledge.py`). `rule` entries come from
  `CLAUDE.md`, `docs/AGENT-GUIDE.md` and `dev/knowledge/house-rules.md`. A program drafts them, one haiku step
  writes each component's one-paragraph summary, and they wait as `proposed` until the coordinator confirms them in
  bulk.
- *Decisions:* the 9 in `decisions.md` become `ergostat.decision` items (confirmed, `proposed_by: migration`, their
  *Areas* as `scope`).
- *Lessons:* the 13 become `knowledge/lesson/*`, with `cites` pointing at the reviews they were seen in.

**Learned, continuously:**

| From | Becomes | Today |
|---|---|---|
| a research question answered | `finding` entries citing the `research` item and the report | a file nobody reads again |
| a planner's session | `finding`s about the files it read; a `question` when it guessed | lost with the plan |
| the librarian | a `lesson` proposed directly as an entry, its "seen as" an appended `evidence` | a gap per paragraph |
| a simplification or subtraction run | a `finding`: "X was removed because Y" `about` the file, so later gaps do not add it back | nothing |
| a review finding repeated across gaps | `evidence_for` on the lesson | `lesson.seen` counts |
| the pipeline manager's handled situations | a `finding` on the block it was about | the situation's summary |

**Gap type `research`.** A gap whose GAPS entry asks a question rather than for a change (or that a planner marks
`<research>`) goes to the researcher, not the implementor. It is done when its findings are `active`, not when a
branch merges. Research produces knowledge, not code.

**Usage.** A brief records the ids it carried (it already does: `contexts[].knowledge`). The `kb_*` calls a session
made are already in the session item's `tool_calls`. The curator folds both into `knowledge.used` on each entry:
`carried`, `read`, and the gaps that used it.

**Outcome attribution.** For each entry with at least 5 uses, compare the gaps that used it with gaps touching the
same files that did not. The comparison covers first-pass approval, fix rounds, parks and a revert after merge. The
result is `lift` with its `n` on the entry. An entry that was used often and shows no lift is a candidate to rewrite
or retire. That is the rule `README.md` already states for lessons, made a measure. The baseline is matched by files
touched, not taken over all gaps, so a lesson about hard code is not blamed for hard code.

**The curator** is a program block (`kb-curate`, every 30 minutes) with one small AI step. In order:

1. **Stale:** referents moved past their anchors; mark the entry `stale` (program).
2. **Unused:** active for 30 days with no use is marked for retirement (program).
3. **Duplicates:** high FTS overlap and the same `about` set produce a merge proposal (program; haiku only to write
   the merged text).
4. **Contradictions:** two active entries about the same referent whose texts conflict get a `contradicts` edge.
   The program finds candidates and haiku judges them. A contradiction with a confirmed decision always goes to the
   inbox.
5. **Proposals:** `knowledge.proposed` older than a day are triaged. One from a session whose gap merged first-pass,
   with confidence ≥ 0.7 and no contradiction, is confirmed automatically, recorded with `by: program/kb-curate` and
   its reason. The rest go to the inbox as `knowledge-change`, the gated action that already exists. Feedback loops
   over gates: the coordinator answers only what the program cannot decide.

**In the model** (`dev/model/knowledge.yaml`, extended): stocks `kb-active`, `kb-proposed` and `kb-stale` (items
sensors by state); flows `kb-learned`, `kb-confirmed`, `kb-staled` and `kb-retired`; auxiliaries `kb-reads-per-session`,
`kb-lift` (first-pass yield of gaps whose sessions read the graph minus that of matched gaps that did not) and
`kb-stale-share`. Goals: `kb-stale ≤ 5% of active`, `kb-proposed ≤ 0` (decided within a day) and `kb-lift ≥ 0`. If
`kb-lift` is below zero for two weeks, that is a finding against the graph itself: it is carrying noise.

## 4. Planning in proportion to the gap

**A size class on every gap, cheaply.** `dev/bin/size.py` is a program that runs as a gap is requested. Its inputs:

- the GAPS entry's length;
- the files, parts and SPEC sections it names (regexes that exist);
- how many components `kb_about` reaches from those names;
- whether it adds a kind, a block type or a SPEC section;
- the `net_lines` of the nearest merged gaps, by shared files (`fac.net_lines` is recorded on every gap).

| Class | Expected | What planning it gets |
|---|---|---|
| **S** | ≤ 100 net lines, one component | **No planner.** The implementor's brief is assembled from the graph (`about` the named files and parts, the lessons whose `about` overlaps, the related gaps). The brief tells it to write its own definition of done (≤ 3 acceptance tests) as the first commit, and the reviewer judges the work against that and the GAPS entry. |
| **M** | ≤ 300, ≤ 2 components | A **short plan**: Sonnet, a cap of one page and ≤ 5 tests, a budget from the class, no plan review. A program checks it: it parses, names tests, and its budget is within the class. |
| **L** | ≤ 800, several components | Plan on Opus, as today, with ≤ 10 tests. The plan review is **sampled**: always for the first 10 L plans, then for one in three while `plan-risks-held` ≥ 0.8. |
| **XL** | more, or crossing systems | **Must split** (below). Never built as one branch. |

The program gives a class and a confidence. Only when the confidence is low (signals disagree, nothing to compare
with) does one haiku step decide. Either way the gap records `size`, `size_by` and `size_confidence`. After the merge,
the actual `net_lines` and fix rounds give the true class, and `size-accuracy` (the share classed within one class,
and the share under-classed) is an auxiliary with a goal. An under-classed S that needed two fix rounds is the
expensive error. The thresholds are parameters in the model, moved by what that measure shows.

**Planning reads the graph first and writes back what it learned.** The planner's brief opens with `about` for the
gap's referents and a `kb_search` on its title. It has the `kb_*` tools. Its instructions say to answer "what is
already known" before reading code, and to end with `<knowledge>` tags for what it found that is not yet in the graph.
A plan that cites entries records them (`uses`). Done well, planning an M gap becomes mostly assembly. That is the
owner's "most planning has already been done".

**The split, verified.** Today a split is trusted: the parent waits, the join moves it on, and `splits-clean` counts
children approved first time. Nobody has checked that the children together do what the parent asked. Three
additions:

1. **A split must hold together** (a program, in `plan.problems`). Each child is classed ≤ L. Each of the parent's
   done criteria (numbered in its plan) is named by at least one child's `covers: [1, 3]` line. The `depends-on`
   among children has no cycle. At most 6 children (already a limit).
2. **The parent is judged at the join.** When the join moves the parent to `merged`, the intent judge (SPEC §12i)
   reads the parent's definition against the merged children's diffs. If its verdict is short of done, the parent
   reopens (`ergostat.item.reopened`) with what is missing as a new child.
3. **Split quality is measured.** `split-quality` is the share of split parents whose judge said done at the join;
   `split-overhead` is the children's total cost over the class's median for an unsplit gap. Until 5 split parents
   have joined, the XL rule says *split, and tell the coordinator*. It becomes automatic only when `split-quality ≥
   0.7`. That is the owner's condition: "a good pattern if we can verify that the splitting works".

**Measures, so each stage earns its place.** These are `planning-cost-share` (planning and plan-review dollars over
build dollars per merged gap; goal ≤ 0.25, today about 1), `first-pass-by-size` and `plan-review-catch` (the share of
plan reviews whose blocking findings would have been review findings later). If a plan review for L catches nothing
over 20 plans, sampling drops to one in ten. If S without a planner has a worse first-pass yield than M with one,
the S threshold moves down.

## 5. Reflecting on the models

The graph lets an agent ask *why* about the SD and control models, not only *what*:

- **About a part or a loop.** `kb_about loop:<name>` expands to the loop's members (`spec/causal.py` gives each loop a
  stable name, from the goal it seeks or the stocks it runs through, and its members) and returns what is known about each member. "Why is first-pass yield off?" reaches the lessons
  `about part/auxiliary.first-pass-yield`, the findings about `part/block.reviewer`, and the decisions in their
  `scope`.
- **Evidence with a measured value.** A `finding` that rests on a metric records `observed: {part, value, window,
  at}`. The curator re-reads the value (the same readings `status` and `measures` use). When it has moved past the
  part's tolerance, the entry gets `evidence-drifted` and goes back to `stale`. Knowledge that rests on a projection
  (§12b) records the projection's context hash in the same way.
- **The existing tools point at the graph.** `explain`, `findings` and `status` in `mcp.py` add one line per part:
  "known: 4 entries (2 stale) — kb_about part/stock.gaps-ready". It is a pointer, not the text, so their output stays
  short.
- **The model's own changes are knowledge.** An `ergostat.model-change` item that was accepted is `cited_by` the
  findings that motivated it, so the reasoning behind a parameter's value is one query away.

## 6. Migration

1. Widen the `knowledge` kind (states, `type`, relations). `knowledge-sync` keeps syncing the three files, now as
   `rule` and `lesson` entries with `origin: seeded`. Today's ids (`lesson-3`) become `knowledge/lesson/3` so the
   briefs' recorded ids still match (an alias map in `knowledge.py`).
2. Move the 9 decisions to `ergostat.decision` with one script and delete `decisions.md`. The briefs read them with
   `ergostat context decisions --scope <areas>`.
3. Turn the 3 research reports into findings, using the researcher's own `<knowledge>` pass over each.
4. Change the librarian to write lesson entries rather than gaps. `review-lessons.md` stops being edited by gaps.
   Once lessons live in the record, the file is removed, and `knowledge-sync` keeps only `house-rules.md`, which is
   still the reviewed source for rules.
5. Change `knowledge.block()` to query the graph (`about`, then lessons by overlap, then decisions), keeping its
   budget and its record of carried and dropped ids. The markdown regexes go.

Each step is behind the briefs' recorded context. Comparing first-pass yield before and after a step tells us
whether it helped.

## 7. The gaps, smallest valuable first

| # | Branch | Depends on | Done when |
|---|---|---|---|
| 1 | `gap-size` | — | Every requested gap has `size`, `size_by` and `size_confidence` from `dev/bin/size.py`, with haiku only below a confidence threshold. `size-accuracy` is an auxiliary in `dev/model/knowledge.yaml`, worked out from merged gaps' `net_lines`. Backtested on the merged gaps in the record, with the confusion table in the gap's notes. |
| 2 | `plan-by-size` | 1 | S gaps go `open → ready` with no planner session, and their brief asks for a self-written definition. M gets a capped short plan with a program check and no plan review. L plan review is sampled. XL is refused unsplit. `planning-cost-share` and `first-pass-by-size` are in the model. |
| 3 | `split-verified` | 2 | `plan.problems` requires children ≤ L, `covers:` for every parent criterion and no cycle. The intent judge runs on the parent at the join and reopens it with a new child when it is short. `split-quality` and `split-overhead` are measured. XL auto-split stays behind `split-quality ≥ 0.7` over 5 joins. |
| 4 | `kb-kind` | — | `knowledge` has its types, states and non-precedence relations in `ergostat.yaml`. The 3 files are synced as entries with aliases for old ids. The 9 decisions are `ergostat.decision` items. The 3 research reports are findings. Briefs carry the same text as before (a test compares). |
| 5 | `item-search` (core) | — | `search:` on a kind fills an FTS5 table in the item index (rebuilt by `--reindex`, checked in `tests/test_item_index.py`). `ergostat/graphquery.py` provides near, path, about and search. `ergostat items --near/--path/--about/--search` and `GET /api/items` take them. SPEC §5a says so. |
| 6 | `kb-parts` | 4, 5 | `parts-sync` keeps a `part/*` and `file/*` item per model part and tracked file, with hashes. Entries record `anchors`, and a changed referent stales the entries about it. `about loop:<name>` expands through `spec/causal.py`. A part's item page lists what is known about it. |
| 7 | `kb-mcp` | 5, 6 | The `kb_*` tools are in `mcp.py`. `agents.py` exports `run/kb/<hash>.db` and mounts it with the installed code read-only. Planner, implementor and researcher sessions have the tools. The snapshot hash is on each brief's context. A container test shows a session calling `kb_about` with no network but the egress. |
| 8 | `kb-writeback` | 7 | `<knowledge>` tags from the planner, researcher, implementor and simplification runs are recorded as `knowledge.proposed` with provenance and anchors. A `research` gap type ends when its findings are active. The planner's brief opens with the graph. `knowledge.block()` queries the graph instead of the markdown. |
| 9 | `kb-curator` | 8 | `kb-curate` handles stale, unused, duplicates, contradictions (haiku on candidates) and auto-confirms by the stated rule, sending the rest to `knowledge-change`. Uses and `lift` are on entries. `kb-active`, `kb-proposed`, `kb-stale` and `kb-lift` with goals are in the model. The librarian writes entries, not gaps. |
| 10 | `kb-reflection` | 6, 9 | `observed:` evidence is re-read and drifts to stale. `explain`, `findings` and `status` point at entries. Accepted model changes are cited. An eval asks five "why is this loop off" questions on the factory's own model and scores answers with and without the tools. |

Gaps 1–3 cut planning cost now and do not wait for the graph. Gaps 4–5 can run beside them. Every gap's definition
includes the measure that decides whether its stage stays. A stage whose measure shows no value after 20 gaps is
removed by a gap of its own.

## What this does not do

- It adds no new store and no vector index. Full text plus typed relations comes first, and embeddings are
  considered only if `kb-lift` shows that retrieval, not content, is what limits it.
- Agents get no write path into the record from inside a container.
- Private or work-specific material stays out (as `dev/knowledge/README.md` already says). The graph lives in this
  instance's record, and only `house-rules.md` remains in the repository.
- No time travel over relations yet (*Relations, what is left* in `docs/GAPS.md`). Queries read relations as they
  stand, and an entry's history answers "what did we believe then" for one item.
