"""Templates: reusable shapes of model, instantiated with parameters (SPEC §2a).

A template is a generic structure in the system dynamics view and a library block in the control view: a small
model (items, stocks, flows, auxiliaries, goals, blocks) written once with ``${param}`` in it, and used many times
under ``uses:``, each use expanded into ordinary parts named for the instance and grouped as a system of its own.

- ``templates`` finds and reads them: ergostat's own (``library/templates/``) and the owner's folders (``library:``
  in the main file, and ``$ERGOSTAT_LIBRARY``);
- ``expand`` turns one ``uses:`` entry into the sections it stands for;
- ``run/`` holds the programs the built-in templates run (the collector, the per-item driver, the report's clock)
  and their free stand-ins, so every template runs offline;
- ``author`` is what the MCP authoring tools do: list, add, scaffold, try, show."""
