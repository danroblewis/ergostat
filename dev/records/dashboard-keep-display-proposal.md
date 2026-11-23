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
