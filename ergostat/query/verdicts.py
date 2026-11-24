"""An answer's verdict (SPEC §4e, *Verdicts*): ``ok``, ``warn`` or ``refuse``, with its reasons. Each reason is one of a
closed list of codes, and each code has its level and its fix, so a panel can say what is wrong and what to do about it.

``refuse``: the answer holds nothing to draw, and the panel says why and the fix. ``warn``: it is drawn, with the
words on the chart. A code not listed here is a mistake in ergostat, never a verdict: ``reason`` raises on it."""

from __future__ import annotations

LEVELS = ("ok", "warn", "refuse")

# code: (level, fix). The fix is said after the reason, as one imperative clause
REASONS: dict[str, tuple[str, str]] = {
    "limit": ("refuse", "narrow the window, or aggregate the query (sum by, topk)"),
    "unreachable": ("refuse", "check the source's url under sources:, and that the source is up"),
    "refused": ("refuse", "correct the query in its source's language"),
    "unknown": ("refuse", "name a source that is listed under sources:"),
    "unanswerable": ("refuse", "correct the query; if it could not be read, the server's log says why"),
    "busy": ("refuse", "try again in a moment"),
    "reader": ("refuse", "sign in as the owner, or as a login the owner listed, to ask a data source"),
    "no-coherence": ("refuse", "move the input on purpose, record longer, or ask the goal's model for its response"),
    "partial": ("warn", "narrow the window, so the whole record is read"),
    "not-cumulative": ("refuse", "ask for one histogram's buckets over one window: sum by (le) (rate(NAME_bucket[5m]))"),
    "many-histograms": ("refuse", "add the histograms into one: sum by (le) (...)"),
    "open-top-bucket": ("warn", "add a bucket above the highest bound, so those values are placed"),
    "averaged-percentiles": ("warn", "add the buckets first and take one quantile: "
                                     "histogram_quantile(0.99, sum by (le) (rate(NAME_bucket[5m])))"),
    "quantile-in-bucket": ("warn", "draw the buckets themselves (a heatmap of NAME_bucket by le) to see the bounds"),
    "graph-over-budget": ("warn", "draw it as a matrix (the Heatmap chart), or ask for one kind or a shorter window"),
    "graph-truncated": ("warn", "ask for one kind or a shorter window, so the whole graph is read"),
    "graph-cycle": ("warn", "change one of the relations that go round, so the cycle is broken"),
}


def reason(code: str, says: str) -> dict:
    """One reason: its code, what it says and its fix. ``KeyError`` for a code that is not in the closed list."""
    if code not in REASONS:
        raise KeyError(f"{code!r} is not a verdict's reason; the reasons are {', '.join(REASONS)}")
    return {"code": code, "says": says, "fix": REASONS[code][1]}


def verdict(reasons: list[dict]) -> dict:
    """The worst level of ``reasons`` (``ok`` with none), and the reasons themselves, each once."""
    kept = list({(r["code"], r["says"]): r for r in reasons}.values())
    level = max((REASONS[r["code"]][0] for r in kept), key=LEVELS.index, default="ok")
    return {"level": level, "reasons": kept}
