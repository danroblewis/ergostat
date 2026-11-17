"""Claims (SPEC §12g): what a block says it did, checked by ergostat against the record and the world.

A block's run may print ``{"claim": {"says": "tests pass", "about": "hypothesis/3"}}``. ergostat records it as an
item of the built-in kind ``ergostat.claim`` (made, by the block, in its run: ``record.py``), and after the run
checks it (``checks.py``): verified, contradicted (each with its evidence), or unchecked when no check knows that
kind of claim. Unchecked is never trusted. How far each block's claims hold is a measure (``trust.py``,
``ergostat.trust.*``), and a contradicted claim is a finding about the block that made it."""
