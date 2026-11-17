"""How we know the improver works (docs/MODEL-TOOLS.md, SPEC §12f): the verification of the loop that improves the
model. ``adapter`` drives that loop's own modules at moments of a simulated record (``clock``); ``truth`` holds the
cases with known models and simulates them; ``defects`` plants known damage; ``improvers`` are the stand-in, the
calibrator and the AI; ``recovery`` runs the loop on a damaged model and scores it (``scorecard``); ``judging``
measures the judge alone, and ``judge_fixes`` tries the changes proposed to it. The live checks are
``numbers/verify.py`` and ``numbers/meta.py``."""
