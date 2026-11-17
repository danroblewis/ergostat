"""The owner's messages, absorbed by the work in flight (SPEC §12h; harness parity 2.4).

A message is an item of the built-in kind ``ergostat.message`` (``record.py``): the owner's words, verbatim, who sent
them and when, and what they are about when the owner says (``--about``). ergostat routes it to the work it concerns
(``route.py``): an item or part it names, an item id or part name in its words, or else a classifier (a block the
project names, an ``ai`` block on a cheap model; by default ergostat's stand-in, matching words to the open items).
It is routed to the open items it concerns and to the block runs working on them now, and delivered
(``deliver.py``): to a running Claude Code session as its next turn (``ergostat/session.py``), to a block that is no
session in its next run's context (``messages``), and, about finished work, as a follow-up (a new item linked to it)
or by reopening it. A message that reaches no work is unrouted, and needs attention. How messages reach the work is
measured (``measures.py``, ``ergostat.messages.*``)."""
