## Entry

section: Remote systems and libraries

- **Identifying existing controllers** (done on `identify`; SPEC §12d, *Existing controllers*): an external block's
  `identify: {input, output}` fits on-off, proportional, PI and three-position step (floating) laws with a delay from the
  record, picks one by held-out error with a parsimony penalty, runs it in the closed-loop projection, draws it in the
  block, and says `external-unidentified` and `external-not-run`. Validated on a synthetic HPA-like stepper and an alert
  rule (`~/orchestra-kube-sim` is not on this machine). A demo, `examples/autoscaler` (done on
  `demo-observed-external-controller`): a simulated HPA with the documented rule, drawn, identified (mostly as a
  stepper, with a modest fit) and judged, `/api/loop-control` giving the external law. *Left*: **`external-law-changed`** (someone retuned the
  controller): comparing each half's numbers fired on unchanged controllers (alert 24/30 seeds, HPA 7/30), and a
  held-out test of two laws against one still did on a few, so it was dropped; it needs a test on counts of moves
  mistold, with a false-positive rate measured over seeds. Also the library of known laws (`law: kubernetes-hpa`,
  declared and tested against the record), the HPA's multiplicative rule as its own family, the risk sampling the law's
  numbers, a closed-loop identification free of the bias (an instrument, or the delay told apart), margins worked out
  from an identified external law, and a run against the kube sim.
