"""Gated actions (SPEC §12k): the outward acts an AI session may ask for (push a branch, open a pull request, move a
ticket, post a message), each a command the model names under ``actions:``, served to the session as tools by an MCP
server ergostat runs for it (``server.py``), and run only as its gate says: ``auto`` (at once), ``approve`` (held until
the owner approves, on the page or with ``ergostat actions ID --approve``) or ``deny`` (never). Every request and
answer is an event about an ``ergostat.action`` item (``record.py``); the gate's logic is ``gate.py``. The session
itself is started so it cannot make those acts any other way (``sandbox.py``: Claude Code's tool and permission flags,
and its OS sandbox)."""
