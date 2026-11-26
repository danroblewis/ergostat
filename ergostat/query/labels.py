"""What an item is labelled by, for a filter or a group: its state, a low-cardinality field (a group relation's
field among them: a gap's ``milestone``), or its ``state_group``. The generated SQL reads them from the item views
(``item_list``, ``item_labels``, ``item_state_groups``: sources.py); ``word`` is how a field's value is said as a label
here and there (``item_labels`` writes the same in SQL)."""

from __future__ import annotations

NONE = "none"
STATE_GROUP = "state_group"     # a label, not a field: an item's stage in its progress (spec/grouptally.py ``stages``)


def word(v) -> str:
    """A field's value as a label (an empty text is none, as a group's progress reads it)."""
    if v is None or v == "":
        return NONE
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v) if isinstance(v, str | int | float) else "many"
