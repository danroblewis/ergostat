# remote-and-libraries-known-controller-laws: An external block may declare a known law (kubernetes-hpa, alert-rule), checked at compile

depends-on: []

Problem: external-systems.md says an observed controller's law is declared where it is known and a library of known controllers ships with ergostat; today an external block takes only `agent` and `identify` (ergostat/spec/compile.py:94, :1466-1473) and the HPA's multiplicative rule is in no family (ergostat/numbers/extlaw.py:24). This gap is the catalogue and the compile only; drawing and explaining it is remote-and-libraries-known-laws-drawn-and-explained. Change: ergostat/control/laws.py, a catalogue of laws with typed, bounded parameters and a constructor of an extlaw.Law: kubernetes-hpa (target, min, max, tolerance 0.1, stabilize-down 5m, stabilize-up 0s, every 15s) and alert-rule (threshold, side, for; the onoff family with levels 0 and 1). extlaw gains the `ratio` family's step (desired = ceil(u*x/target) outside the tolerance band, scale-down takes the largest desired over the window, clamped); no fitting here. compile accepts `law: {kind, ...}` on an external block with `identify:` and puts it in the IR; an unknown kind or parameter, a missing required one, a value out of its bounds, or law without identify is bad-law at that key. Done: both kinds compile and their Law steps as the rule says on a hand-worked sequence (scale up at once, scale down only after the window, clamped at min and max; the alert fires after `for`); each refusal has its place; a model with no `law:` compiles to an identical IR; SPEC §12d lists the catalogue and its parameters. Files: ergostat/control/laws.py (new), ergostat/numbers/extlaw.py, ergostat/spec/compile.py, ergostat/spec/ir.py, docs/SPEC.md, tests/test_known_laws.py (new, four tests). Budget: 160 net lines.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1: all of the definition, 150 net lines outside tests and docs (within 160). Choices made with no one to
ask, each the more reversible one:
- Parameters listed without a default are required: kubernetes-hpa's `target`, `min` and `max`, and all three of
  alert-rule's (`threshold`, `side`, `for`). Adding a default later refuses nothing that compiles now.
- Bounds: target in (0, 1e12]; min and max whole numbers from 1 to 1,000,000 with min ≤ max (bad-law at `max`);
  tolerance from 0 to 1; each stabilize window from 0s to 1h (the HPA's own most); every from 1s to 1h; threshold within
  ±1e12, not NaN; `for` from 0s to 7d. `0`/`0s` are read as a zero duration (parse_duration refuses 0).
- The law is a typed field, `Block.law: KnownLaw | None`, not a raw entry in `params` (`law` is taken out of params).
- `stabilize-up` takes the least desired over its window (the HPA's rule); the definition named only the down window.
- The alert rule's Law steps on the `dt` it is given (its evaluation interval), 15s when none is given: the
  catalogue has no `every` for it.
- `law:` is bad-law when `identify:` is absent; a written but wrong `identify:` keeps its own bad-ref and is not also
  bad-law. A missing required parameter, a law not a map, and a law without identify are at the `law:` line.
- Outside the Files list: schema/ergostat.schema.json gains `law` (kind enumerated), so the schema does not refuse what
  compiles; docs/AGENT-GUIDE.md gains one bullet. `Law.said()`/`short()` gain a ratio line each so a ratio Law can be
  written without a KeyError; drawing and explaining stay in remote-and-libraries-known-laws-drawn-and-explained.
- Nothing runs the declared law yet (projection, check against the record): SPEC says so.

Round 2: the review's one finding is fixed. A `kind:` written as a YAML list or map raised TypeError (unhashable)
before it reached the catalogue lookup. It is now bad-law at `kind`, like any other unknown kind
(ergostat/control/laws.py checks `isinstance(kind, str)` first). test_each_refusal_is_bad_law_at_its_key gains a list
case and a map case. Without the fix the test failed with that TypeError; with it, it passes. The other values a law
can take were read for the same crash and none was found: a duration given as a list or map is turned into a string
and refused as not a duration, a side given as a list or map is compared by equality, and a NaN or infinite number is
refused by the bounds check. The fix changes one line; the total is still within 160.

Round 3: the review's one finding is fixed. Round 2's claim was too wide. A YAML integer longer than about 309 digits
(PyYAML reads it as an unbounded int) crashed compile with OverflowError in `math.isfinite`/`float()` for `target`,
`min`, `max`, `tolerance` and `threshold`. It crashed the same way through `parse_duration`'s `float(value)` for
`every`, `for` and the `stabilize-*` windows. Now an int is compared to its bounds as it is (Python compares an int to
a float exactly, with no conversion), and only a float is tested for NaN or infinity. So such an int is out of bounds
and is bad-law at its key. A duration whose conversion overflows is read as infinite and refused by the same bounds
check. durations.py (on main) is not changed. test_each_refusal_is_bad_law_at_its_key gains seven 400-digit cases
(target, min, max, tolerance, every, threshold, for). Before the fix it failed with OverflowError at laws.py:54; after
it, it passes. A duration written as a long digit string (`999…9s`) does not crash, because `float()` of a string
gives inf, which the bounds refuse (an eighth case in the same test). `stabilize-down` and `stabilize-up` go through
the same duration path as `every` but have no case of their own. Not checked here: an integer over Python's 4,300-digit string-conversion limit
fails in PyYAML's own loader, before any law is read. Net lines outside tests and docs: 153 (within 160).
