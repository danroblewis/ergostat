## Entry

section: Modelling

- **Built-in join** (done, de204df and 966a07f, on `causes-join`; SPEC §5a, *Join*): `join: {children: REL, all:
  STATE, to: STATE}` (or `any:`) on the parent's kind, fired on each child's move from the item index, the parent's
  move recorded as `ergostat.item.joined` caused by the child's, folded only forward and counted like any other;
  `examples/roadmap` uses it in place of `bin/epics.py`. *Left*: the Blocks view does not draw a join (a rule on a
  kind, not a block); each child's move reads all its parent's children (O(children) per move: fine for an epic's
  tickets, not tuned for thousands).
