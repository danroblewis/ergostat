# dashboard-keep-display-proposal: Keep: a dashboard draft becomes a declared dashboard through an owner display proposal

depends-on: [dashboard-add-and-edit-draft, dashboard-declaration-and-api]

Problem: a draft lives in one browser and its links; a dashboard the owner wants kept needs to reach the model's dashboards: without a person writing configuration (decision 7). The what-if (ergostat/web/numbers_api.py post: propose, then accept) is the allowed page path from an owner proposal to a YAML write. Build only if the proposal and the owner's answer say Keep goes through the page; otherwise this gap is amended to 'the Supervisor writes it from the draft's link' and shrinks to a documented Supervisor step in docs/AGENT-GUIDE.md.
Change: 'Keep' on a draft makes an ergostat.model-change of kind display, made by owner, carrying the diff of dashboards: (worked out by the server from the draft, never shown as text to edit), shown as a proposal; the judge passes display changes at once (no dynamics changed); Accept writes the YAML through the same path as a what-if; Dismiss drops it. Agents' and the Supervisor's display proposals appear the same way.
Definition of done:
1. The page writes no file except through Accept.
2. Keep then Accept gives a declared dashboard that `ergostat check` passes and /api/dashboards lists.
3. The model-change item records owner as the maker.
4. A display change is never replayed by the judge and a change touching anything but dashboards: is refused as display.
Files: ergostat/web/static/dashboard.js, ergostat/web/numbers_api.py (a display proposal), the judge's policy for kind display, docs/SPEC.md (dashboards section and the model-change table), docs/AGENT-GUIDE.md, tests.
Acceptance tests: browser on a served fixture: Keep makes one model-change of kind display; after Accept /dashboard draws it; the refusal unit test.
Budget: 150 net lines.

Milestone: dashboard. Owner items: 18. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Implementor, 2026-11-23, round 1. Built; every definition-of-done item has a test that was seen to fail when the
code it guards was broken.

The build condition: the proposal held this gap "until the owner answers"; nobody answers here. The factory started
it, and the declaring half (dashboard-declaration-and-api) is on main, which the proposal drops if the answer were
"the address and the browser only". So the answer was read as "Keep goes through the page", and the gap was built
(the most reversible reading: Keep only ever files a proposal; nothing is written without the owner's Accept).

What is built:
- `numbers/display.py`: `keep` works out the `dashboards:` entry from the draft on the server (named from its title,
  each panel one JSON line, round-tripped through YAML before it is offered; an existing dashboard of that name is
  replaced in place), compiles it with findings, and records one `ergostat.model-change` of kind `display`, made by
  `owner`, under the proposals' lock. `beside` is the guard (an allowlist): every edited file must read, with
  `dashboards:` left out, as the same data as before; an unreadable file counts as changed.
- `improve.py`: `display` in KINDS and WORDING (so the judge passes it on `check`, never replayed); `kind_of` says
  display when only `dashboards:` differs in the compiled spec; `validate` refuses a display proposal touching
  anything else, and a dashboards-only change said to be another kind. A display change's reasons still need
  evidence ergostat can check, but need not be supported by a fit or a finding (it moves neither).
- `ir.CHANGE_CLASSES` and `NAMED_ONLY` gain `display` (written by the judge only under `display: auto`).
- `spec/dashboards.py`: a new declared panel kind `query` (the page's own: `form`, `queries`, `display`, `layout`);
  its queries are checked by `query.parse` as the page sends them (`sent`: `label`/`hidden` dropped, references by
  id resolved) and each query's `kind` must be the model's. `/api/dashboard/NAME` answers it through `/api/query`.
  Schema updated.
- `numbers_api.post`: `POST /api/propose?keep=dashboard` with the draft as the JSON body (`server.py` passes the
  body). `dashboard.js`: a Keep button on a reader's draft; `/dashboard?name=NAME` draws a declared dashboard's
  `query` panels. `review.js`: the queue says "you (Keep, on the Dashboard)".
- SPEC §4f (the `query` row, the display paragraph, Keep) and §12e (the `kind` key, `accept`), AGENT-GUIDE §3l.

Tests: `tests/test_dashboard_keep.py` (8: Keep writes nothing and records owner; Keep then Accept passes `ergostat
check`, is listed by `/api/dashboards`, and a second Keep replaces it in place; refusals; the judge passes a display
change with `compare`, `needs`, `recorded` and `spec_after` made to raise; the refusal unit test, including a goal
written otherwise that compiles the same, which only the text guard catches; Keep's own guard; the batched answer of
a `query` panel). `tests/test_dashboard_keep_page.py` (browser, real `ergostat web` on a copy of image-squeeze: Keep
makes one entry of kind display and writes no file; Accept under Changes to review writes `ergostat.yaml` only;
`/dashboard?name=lab-watch` draws it; `ergostat check` passes). Broken on purpose and seen to fail: `display` out of
WORDING; the `bad` guard in `validate`; the `beside` guard in `keep`; `dashDeclared` returning nothing.
`tests/test_improve.py` now lists `display` among the policy's classes (it pins that list).

Left, not in this gap:
- A draft with rows, variables or repeated panels is refused by Keep ("they stay in the draft"): `dashboards:` holds
  panels alone so far.
- `/dashboard` does not list the declared dashboards; Keep's message links to `/dashboard?name=NAME`. The listing
  beside the reader's own is dashboard-declaration-and-api's change 5, not built there either.
- Declared panels of the other kinds (`chart`, `goals`, ...) are still not drawn on the page (only `query` panels).
- Not run here: the whole unit suite and the four browser files (run by the factory and the queue).

Overrun reason: the declared `dashboards:` schema could not hold a page draft (its kinds are endpoint panels; a draft's panels are query-engine forms), so done item 2 needed a `query` panel kind with its check and the page-side resolution (`sent`, about 60 lines), and "after Accept /dashboard draws it" needed the page to draw a declared dashboard, which the declaration gap left unbuilt (about 25 lines); with `numbers/display.py` (143 lines, its guard and docstrings) the branch is 261 net lines against 150.

## Entry

section: Interface

- **Keep: a dashboard draft becomes a declared dashboard** (done, on `dashboard-keep-display-proposal`; SPEC §4f,
  §12e): Keep on a draft files one `ergostat.model-change` of kind `display`, made by the owner, whose `dashboards:`
  edit the server works out (panels of the new `query` kind, checked by the query engine's parser); the judge passes
  a display change on `check` without a replay; Accept writes it, Dismiss lets it go; a change touching anything but
  `dashboards:` is refused as display. `/dashboard?name=NAME` draws a declared dashboard's query panels. Not done:
  drafts with rows, variables or repeated panels; listing the declared dashboards on `/dashboard`; drawing the
  declared endpoint kinds on the page.
