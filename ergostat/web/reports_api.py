"""Reports upstream on the page (SPEC §12m): ``GET /api/report/ID`` (the text to paste, the link to a new issue and the
scrub log) and ``POST /api/report/ID/reviewed``, ``/submitted`` or ``/dismissed`` (``note=``), the owner marking one.
Nothing here sends anything anywhere: the link is for the owner to open."""

from __future__ import annotations

from urllib.parse import unquote

from ..webaccess import who


def get(p, rid: str) -> dict | None:
    from ..reports import record
    try:
        return record.text_of(p, rid)
    except record.ReportError:
        return None


def post(live, path: str, q: dict) -> tuple[int, dict]:
    from ..reports import record
    rid, _, verb = unquote(path.removeprefix("report/")).rpartition("/")   # report/ID/submitted (the ID has a / in it)
    if not rid or verb not in ("reviewed", "submitted", "dismissed"):
        return 400, {"error": "POST /api/report/ID/reviewed, /submitted or /dismissed"}
    try:
        got = record.mark(live.get(), rid, verb, by=who(), note=(q.get("note") or [None])[0])
    except record.ReportError as e:
        return 400, {"error": str(e)}
    return 200, {"id": got["id"], "state": got["state"]}
