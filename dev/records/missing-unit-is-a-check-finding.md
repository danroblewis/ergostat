# missing-unit-is-a-check-finding: A missing unit is a Check finding drawn as 'unit ?' on the stock, not a request of the owner per stock

depends-on: []

Problem (R2 piece 7): a stock without a unit raises a request to the owner; on big that is 24 requests, which are 24 of the 26 attention entries (shots/pm-big-home.png, story-2-c6-modelling.png). A missing unit is a property of the model, found by checking it, not something a person approves or denies. Every reviewer named the result ('the tool is broken, or is about itself'), and the fix depends on nothing.
Change: the modelling template (ergostat/library/templates/modelling/template.yaml) stops raising a request per unitless stock and requests-handled no longer counts them (this gap owns that edit to requests-handled; demos-upkeep-holds-and-actions-wait follows it); `ergostat check` reports one finding per stock ('no unit', with file and line) which the Model page lists (in filed Q78's table); the Dynamics diagram prints 'unit ?' in the muted tone after the stock's value, with a legend row and the Guide frame that explains a stock's value updated. A fixer run that can infer the unit from the sensor proposes it as a model change as today.
Definition of done:
1. On a fixture with three unitless stocks no attention entry asks for a unit; /api/check lists each unitless stock once.
2. The stock's value on the diagram reads '12 unit ?' and the legend explains it.
3. requests-handled no longer counts unit requests.
4. `ergostat check` on a spec with a unitless stock exits with a warning naming file and line.
Files: ergostat/library/templates/modelling/template.yaml, ergostat/spec/findings.py (or where check findings are made), ergostat/web/static/dynamics.js, review.js, ergostat/guide.py, tests.
Acceptance tests: a check unit test; a browser check on the fixture (and on :8797 by eye).
Budget: 60 net lines.

Milestone: r2-system-first-upkeep-apart. Owner items: R2 piece 7 (second half). From the owner's list and the design review of 2026-11-22.
