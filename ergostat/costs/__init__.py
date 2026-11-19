"""What each run costs (SPEC §9.1, "What a run records"): its AI usage (``ai.py``: tokens, model and dollars, from
Claude Code's result messages, reported or estimated with ``prices.py``), the CPU time and peak memory of its process
tree (``sampler.py``: one shared sampler, and the run's own wait status), and, from the record, each block's totals,
history and the built-in measures ``ergostat.cost.*`` (``record.py``)."""
