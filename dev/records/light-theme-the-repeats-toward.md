## Entry

section: Interface

- **Light theme: the repeats toward the paper are low in contrast** (open; for a design pass, no colour work until
  then; found fixing the dark theme's): the third round of correspondence colours (`--g-fade`, 55% of the hue) stands
  1.6:1 to 2.5:1 on white, and `--g9` (gold) 2.4:1 as it is; WCAG asks 3:1 for graphics. Tried on `smallgaps`
  (48b4254, reverted in 95e1a1f): six hues darkened and `--g-fade` 75% passed 3:1, but the gate review found the
  palette blurred: every hue at OKLCH L 0.50 to 0.56, gold and olive ΔE 4.9 apart, orange 3.0:1 and gold 3.8:1 against
  `--warn`, each repeat only about 12 from its hue. A repeat toward the paper that keeps 3:1 forces every hue to one
  lightness. To try next: mark the paper round by an ink outline or a dash instead of lightness, or alternate the
  hues' lightness (light hues repeated toward the ink only).
