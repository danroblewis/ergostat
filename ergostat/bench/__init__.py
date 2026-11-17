"""How we know the improver works (docs/MODEL-TOOLS.md, SPEC §12f): the verification of the loop that improves the
model. ``adapter`` is the one place that knows the improvement loop's interface (the ``propose`` output, the
``ergostat.model-change`` items, the judge, Accept); ``truth`` holds the cases with known models and simulates them;
``defects`` plants known damage; ``improvers`` are the stand-in and the AI; ``recovery`` runs the loop on a damaged
model and scores it; ``judging`` measures the judge alone; ``verify`` and ``meta`` are the live checks."""
