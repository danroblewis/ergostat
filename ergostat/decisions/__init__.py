"""Decisions and corrections (SPEC §5a, the built-in kinds; harness parity §2.12, §2.13): what the owner
decided, and what the owner corrected, kept as items folded from the record so that every later session
can start from them.

- ``kinds``: the two built-in item kinds, ``ergostat.decision`` and ``ergostat.correction``;
- ``acts``: proposing one (checked first), and the owner's acts on it (confirm, dismiss, supersede, retire);
- ``transcript``: a Claude Code transcript read as turns (who said what, where, when);
- ``standin`` and ``ai``: the two extractors, heuristics on the owner's turns and a model reading them;
- ``extract``: running an extractor over a transcript, as event lines;
- ``fromrecord``: corrections found in the record itself (a dismissal with a reason, an item reopened,
  a message classed as a correction);
- ``context``: the projections, the confirmed decisions and corrections as Markdown for a session's start."""
