"""The query engine behind every chart (``GET /api/query``, ``GET /api/query/fields``; SPEC §4e): one read-only way to
ask for a window of numbers from the item index, the metrics store or, rarely and bounded, the event log."""

from .engine import answer
from .fields import fields
from .parse import BadQuery

__all__ = ["BadQuery", "answer", "fields"]
