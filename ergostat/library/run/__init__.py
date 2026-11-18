"""The programs the built-in templates run, as ``${lib} PROGRAM ...`` (``python -m ergostat.library.run``):

- ``collect``: the event collector, a sensor on an arrival flow: polls a command or an HTTP endpoint (or a stand-in
  feed), records each new record as an event about an item, de-duplicated and from a cursor, and prints the
  arrivals per hour;
- ``each``: a block that works on items one at a time: the items of a kind in a state, a command run for each, the
  item moved on when it succeeds (``steps``, ``respond-to``);
- ``ping``: a block that asks again about each unanswered item, up to a count, then gives up on it (``re-ping``);
- ``due`` and ``report``: a report's clock (a sensor: is a scheduled time past with no report since?) and its
  writer (a block: renders it, keeps the file, records the item) (``daily-report``);
- ``summary``: a free report of the model now (its goals and items), the stand-in for a report's own renderer;
- ``standin``: free stand-ins for the world (``act``, ``level``, ``lower``), so a template runs offline.

Each reads and keeps only its own state, in the project's state directory under ``library/<instance>/``, and
records nothing itself: what it saw or did is printed as the lines a sensor or block prints (SPEC §6, §9.3)."""
