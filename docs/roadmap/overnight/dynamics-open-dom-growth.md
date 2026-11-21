# dynamics-open-dom-growth: find out whether the Dynamics page with all systems open leaks DOM nodes, and fix what is true

depends-on: []

`tests/test_page_polling.py` failed in 3 of 30 merge-queue browser runs in the last 6 hours (2026-11-21) with `DOM nodes grew by 2717`, `1334` and `779`, on `diagram?view=dynamics&open=*`, and passed on retest. One run read nodes 3869 to 6586 and listeners 1153 to 2069 while the page refreshed. It happens under machine load, but it may be a real leak that load only makes visible, and the owner has named UI problems on large systems as something to fix before release. Do not quarantine this test and do not loosen its bound to make it pass.

## Definition of done
1. Measure it: on `diagram?view=dynamics&open=*` with a large model, record DOM nodes and listeners over at least 30 refreshes, once at normal speed and once with refreshes delayed or overlapping (CPU throttled through CDP). Say in the definition's *Where it stopped* what you measured.
2. If nodes or listeners keep growing with refreshes, or a slow refresh overlaps the next and leaves its nodes behind: fix that in the page code, so both stay bounded in both runs.
3. If nothing grows once the page has settled, and the failure is the test reading mid-render: make the test wait for the render in progress to finish before it reads, keeping the same bound.
4. A test holds the result under CPU throttling, so it does not depend on how busy the machine is.

## Files to touch
`ergostat/web/static/` (the diagram refresh code, if it leaks), `tests/test_page_polling.py`.

## Risks
- lesson-3: an unreadable metric fails the test, it never passes it.
- Do not change the refresh rate to hide the growth.

## Acceptance tests
- `tests/test_page_polling.py::test_dynamics_open_stays_bounded_over_30_refreshes`
- `tests/test_page_polling.py::test_dynamics_open_stays_bounded_when_refreshes_overlap`

## Size budget
80 net lines of code outside `tests/` and `docs/`.
