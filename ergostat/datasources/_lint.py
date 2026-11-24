"""What a query's own text shows is a misuse (catalog guardrail G22), said as warnings: ``[(code, says)]``, the codes
of query/verdicts.py. Only PromQL is read; another language has none yet.

- ``averaged-percentiles``: ``avg`` or ``avg_over_time`` taken of a ``histogram_quantile``. An average of quantiles is
  no quantile of anything.
- ``quantile-in-bucket``: any ``histogram_quantile``. Its value is interpolated inside the bucket that holds it, so
  the true quantile may be anywhere between that bucket's bounds."""

from __future__ import annotations

import re

_AVG = re.compile(r"\bavg(?:_over_time)?\s*(?:(?:by|without)\s*\([^()]*\)\s*)?\(")
_QUANTILE = re.compile(r"\bhistogram_quantile\s*\(")


def _inside(text: str, open_at: int) -> str:
    """The text between the parenthesis at ``open_at`` and the one that closes it (to the end, if none does)."""
    depth = 0
    for i in range(open_at, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return text[open_at + 1:i]
    return text[open_at + 1:]


def warnings(language: str, text: str) -> list[tuple[str, str]]:
    if language != "PromQL" or not _QUANTILE.search(text):
        return []
    out = [("quantile-in-bucket", "a quantile from histogram buckets is interpolated inside its bucket, so its true "
                                  "value lies anywhere between that bucket's bounds")]
    if any(_QUANTILE.search(_inside(text, m.end() - 1)) for m in _AVG.finditer(text)):
        out.insert(0, ("averaged-percentiles", "this averages quantiles, and an average of quantiles is not a quantile "
                                               "of anything"))
    return out
