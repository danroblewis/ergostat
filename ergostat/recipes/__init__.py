"""Context recipes (harness parity §2.10, SPEC §12j): named, versioned recipes for a session's starting context,
read from the record and rendered as Markdown (``contexts:`` in the YAML). ``ir`` holds what a recipe is,
``compile`` reads and checks them, ``parts`` renders each kind of part, ``render`` puts a recipe together, ``uses``
records each use of a recipe and the outcome of the work it started, and ``review`` sets a block's review depth from
a measure (its trust)."""
