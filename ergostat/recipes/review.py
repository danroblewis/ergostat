"""Review depth set by a measure (SPEC §12j): a machine block's ``review:`` says who reviews its work, and how
deeply, by its trust (or any built-in measure). After each run that ended well, ergostat reads the rules in order;
the first whose ``when`` holds (a rule without one always does) decides: ``by: reviewer`` commands that block to review
the work (``{"amount": 1, "item": ..., "review": {"of": RUN, "depth": ..., "why": ...}}``); ``by: none`` (or no
rule holding) means no review. Each decision is recorded, ``review.required`` or ``review.skipped``, with the
measure's value, so how deep each run was reviewed, and why, is in the record."""

from __future__ import annotations

import operator

OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq, "!=": operator.ne}


def value(p, name: str) -> float | None:
    from ..numbers.measures import measure
    try:
        return measure(p, name)
    except Exception:                                    # a measure that cannot be read: the rule does not hold
        return None


def decide(p, b, read=value) -> dict | None:
    """The review the block's work gets now: the rule that decided, with what it read; None without rules."""
    rules = b.params.get("review") or []
    if not rules:
        return None
    for i, r in enumerate(rules):
        if r["when"] is None:
            return {"rule": i, "by": r["by"], "depth": r["depth"], "why": "always" if len(rules) == 1 else "otherwise"}
        name, op, num = r["when"]
        v = read(p, name)
        if v is not None and OPS[op](v, num):
            return {"rule": i, "by": r["by"], "depth": r["depth"], "measure": name, "value": v,
                    "why": f"{name} = {v:.3g} {op} {num:g}"}
    last = rules[-1]
    v = read(p, last["when"][0]) if last["when"] else None
    return {"rule": None, "by": None, "depth": "none", "why": "no rule holds" +
            (f" ({last['when'][0]} = {v:.3g})" if v is not None else ""), **({"value": v} if v is not None else {})}
