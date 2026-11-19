"""Reports upstream (SPEC §12m): when ergostat itself is wrong, a report is drafted, scrubbed and kept in the state
directory's ``reports/`` folder for the owner to read and, if they choose, paste into a new issue on ergostat's
GitHub project by hand. ergostat never files one: nothing here opens a connection.

Each report is an ``ergostat.report`` item (``kind.py``), drafted by an agent (MCP ``report_upstream``), the owner
(``ergostat report --draft``), ergostat on its own crashes (``crash.py``, one report a stack signature) or a block that
found something ergostat cannot express (a ``{"report": ...}`` line); scrubbed (``scrub.py``) before anything is
written; and moved by the owner from drafted to reviewed, submitted or dismissed (``record.py``)."""

from .kind import REPORT, STATES

__all__ = ["REPORT", "STATES"]
