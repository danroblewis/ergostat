# remote-and-libraries-autoscaler-template: Built-in templates for known controllers: an observed autoscaler and an alert rule, used by the autoscaler demo

depends-on: [remote-and-libraries-known-controller-laws, demo-observed-external-controller]

Problem: external-systems.md: 'A library of known controllers ships with ergostat as model fragments with their equations and parameters ... You include one and bind it to your metrics.' The built-in library (ergostat/library/templates/, SPEC §2a 'The built-in library') has respond-to, re-ping, steps, keep-under and others, but no fragment for a controller ergostat observes, so every user writes the replicas stock, the utilisation auxiliary, the external block and its identify: by hand.
Change: two built-in templates using the declared laws.
Definition of done:
1. `observed-autoscaler`: parameters target, min, max (and the HPA's optional ones), replicas (a sensor query or command, with a stand-in that creeps with a made-up load), load (likewise), within, description. It makes: stock replicas with its sensor, auxiliary utilisation (= load / replicas, or measured when a utilisation query is given), a goal on utilisation at the target, an external block reading utilisation and setting replicas with law kubernetes-hpa and identify; `reading:` says it in control (an observed controller, a stepper of replicas holding utilisation, r/y/u) and system dynamics (replicas a stock, scaling its flows).
2. `alert-rule`: threshold, side, for, the signal (a query), what it pages (an item kind or nothing); an external block with law alert-rule, the signal auxiliary, and a stock of firing alerts.
3. Both compile on stand-ins alone (template-stand-in finding, as other templates), run offline, and draw in both views; their Blocks loop shows r (target), y (utilisation), u (replicas).
4. The templates tool lists them; docs/ADDING.md and `ergostat help adding` describe them; SPEC's built-in list names them.
Files: ergostat/library/templates/observed-autoscaler.yaml, ergostat/library/templates/alert-rule.yaml, docs/ADDING.md, docs/SPEC.md, tests/test_templates.py.
Acceptance tests: test_observed_autoscaler_on_stand_ins (compiles, one external block with law kubernetes-hpa, the goal on utilisation, template-stand-in listed); test_observed_autoscaler_blocks_loop (Blocks answer: r, y, u named as above); test_alert_rule_template_compiles; existing template tests pass.
Size budget: 130 net lines (YAML counted).

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1. Items 1-4 are in the branch: `observed-autoscaler.yaml` and `alert-rule.yaml`; their stand-ins in
`ergostat/library/run/standin.py` (`load`, `replicas`, `signal`, `firing`); the templates tool lists them; docs/ADDING.md
(which `ergostat help adding` prints) has a table row and a section for each; SPEC §2a's built-in list names them.
Tests: the three acceptance tests, plus `test_observed_autoscaler_stand_ins_follow_a_made_up_load` and
`test_observed_autoscaler_and_alert_rule_run_offline_and_draw_in_both_views` (a trial of each, offline, then the
Dynamics and Blocks graphs), and the MCP test now asks for both names and both ADDING sections. Each acceptance test
was seen to fail with the template broken (law kind changed, identify output moved to the flow), then restored.

Choices made without anyone to ask (each easy to reverse):
- Each sensor is a command parameter (`replicas`, `load`, `utilisation`, `signal`, `firing`) with a `-query` twin (a
  map, a source's query) that takes its place when given, since a template condition cannot tell a map from a text.
- target, min and max have defaults (0.7, 1, 10), and alert-rule's threshold has one (100), so each compiles on
  stand-ins alone. The goal `at-target` is `<= target`, as examples/autoscaler writes it. `every` is the law's
  evaluation period and also the sensors' interval.
- `pages: KIND` makes that item kind (states firing, resolved; events KIND.fired, KIND.resolved), and the firing
  stock counts its items firing. Left out, the firing stock is read by `firing` or `firing-query`. alert-rule holds
  no goal.
- examples/autoscaler is not changed to use the template. The title says "used by the autoscaler demo", but no
  done item and no file in the Files list asks for that, and its own tests pin its part names (`web-hpa`,
  `cpu-at-target`). Moving it over is a later change.
- Outside the Files list: `standin.py` and `run/__main__.py` (the stand-ins: none existed for a load or a signal);
  `trust.py` (`--target`, `--min`, `--threshold`, `--side` added to LIB_DATA_FLAGS, because
  test_every_lib_flag_classified requires every lib flag to be classified; they are plain numbers and a side word that
  multiply nothing, and `--max` stays an exec flag); tests/test_library_provenance.py (ARGVS gains the two new
  parsers).

Found, not fixed (outside the gap): expand.py's REF pattern does not rename a reference after a `-` sign
(`-stock.x` in a prefixed template's `driven-by:` stays unprefixed and fails as unknown-ref). observed-autoscaler
writes `"- stock.replicas"` instead, which the compiler reads the same way.

Overrun reason: 172 net lines against 130. The budget had no room for stand-ins, but item 1 requires one that creeps with a made-up load, and none of the existing stand-ins (level, lower, act) is one (+42 in standin.py and run/__main__.py). The two templates are 131 lines between them, each parameter written on one line.

Run here: tests/test_templates.py (45 passed), tests/test_library_provenance.py, test_library_trust.py,
test_library_untrusted.py (125 passed), tests/test_template_exports.py and tests/test_known_laws.py (passed), ruff
clean. Not run here: the whole unit suite and the four browser files (no page changed), which the factory and the
merge queue run. `main` merged: already up to date.

### Round 2

The one finding (blocking): with `pages: KIND` the firing stock counted KIND's items firing, but nothing made those
items, so it read 0 forever while the signal was past the threshold, and identify compared the signal with a
permanent zero. Answered by the second remedy the review offered, the more reversible one: the firing stock is now
always on its measured sensor (`firing`, `firing-query`, or the stand-in), with or without `pages`. `pages: KIND` only
declares the item kind (states firing, resolved, on `KIND.fired` and `KIND.resolved`). The template's reading, its
param text, docs/ADDING.md and SPEC §2a now say ergostat makes no pages, and that the alerting system has to post
those events (`ergostat event --add KIND.fired --item KIND/ID`). Building the items from the firing sensor instead
would need a collector or block that ergostat does not have for this, so it is a later change if wanted.

Tests: test_alert_rule_template_compiles now checks that with `pages` the firing stock's sensor is the `standin firing`
command and counts no items. New: test_alert_rule_with_pages_reads_its_firing_stock_moving_with_the_signal compiles
with `pages`, takes the stock's sensor command and runs it at the made-up signal's crest, trough and crest (clock
monkeypatched). It reads 1, 0, 1. The offline trial of alert-rule now gives `pages: slow-page`. With the old
items-count sensor put back, the compile test and the new test both failed. The offline trial still passed (a count
of 0 items is a reading too), so it does not guard this. Then restored.

Overrun reason: 171 net lines against 130, for the round-1 reason above (the stand-ins item 1 requires, +42); round 2 removed 3 lines net.

Run here, round 2: tests/test_templates.py, tests/test_template_exports.py, tests/test_library_trust.py (106 passed);
tests/test_library_provenance.py, tests/test_library_untrusted.py, tests/test_known_laws.py (86 passed); ruff clean.
Not run here: the whole unit suite and the four browser files (no page changed). `main` merged: already up to date.
