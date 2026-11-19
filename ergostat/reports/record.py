"""A report upstream, recorded (SPEC §12m): an ``ergostat.report`` item, ``ergostat.report/<short id>``, and two files in
the state directory's ``reports/`` folder: ``<short id>.md``, the issue to paste (its title, its labels, its body), and
``<short id>.scrub.json``, what was removed from it and why (never pasted: it holds the originals).

Its events: ``ergostat.report.drafted`` (who drafted it and how, its title, labels, the file, the scrub's counts, and
for a crash its stack signature), ``.seen`` (the same crash again: its count, no move), then the owner's
``.reviewed``, ``.submitted`` or ``.dismissed``. Nothing is sent anywhere: submitting is the owner pasting the file
into a new issue by hand, and saying so."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from . import about, shape
from .kind import MOVES, REPORT, report_kind
from .scrub import PROJECT_URL, Piece, Scrubber, for_project

ORIGINS = ("agent", "owner", "crash", "modelling")
LABELS = {"crash": ["bug", "crash"], "modelling": ["cannot-express", "modelling"], "agent": ["from-agent"],
          "owner": []}
TITLE_MAX = 120


class ReportError(ValueError):
    pass


def item_of(rid: str) -> str:
    return rid if rid.startswith(REPORT + "/") else f"{REPORT}/{rid}"


def short(rid: str) -> str:
    return rid.split("/", 1)[1] if rid.startswith(REPORT + "/") else rid


def folder(p) -> Path:
    d = Path(p.dir) / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def files(p, rid: str) -> tuple[Path, Path]:
    d = Path(p.dir) / "reports"
    return d / f"{short(rid)}.md", d / f"{short(rid)}.scrub.json"


def issue_url(title: str, labels: list[str]) -> str:
    """A link the owner may open to start a new issue on ergostat's project, its title (and labels) filled in. Only a
    link: ergostat never opens it."""
    q = f"title={quote(title, safe='')}"
    if labels:
        q += f"&labels={quote(','.join(labels), safe='')}"
    return f"{PROJECT_URL}/issues/new?{q}"


# ---- drafting

def _findings(p, spec, wanted: list[str] | None, scrub: Scrubber) -> list[str]:
    """The findings named (``code`` or ``code@about``), with their messages scrubbed; none named: none."""
    if not wanted or spec is None:
        return []
    found = [x for x in getattr(p.model, "problems", []) or []]
    try:
        from ..spec import watch
        found += watch.find(p, spec)
    except Exception:
        pass
    out = []
    for w in wanted:
        code, _, about_ = str(w).partition("@")
        hits = [f for f in found if f.code == code and (not about_ or f.about == about_)]
        if hits:
            out += [f"`{f.code}`: " + scrub.scrub(f.message) for f in hits[:3]]
        else:
            out.append(f"`{scrub.scrub(code)}`" + (" (not found now)" if code else ""))
    return out


def _body(sections: list[tuple[str, list[Piece] | str | None]], scrub: Scrubber) -> str:
    out = []
    for head, content in sections:
        if content is None or content == "" or content == []:
            continue
        text = scrub.join(content) if isinstance(content, list) else content
        out.append(f"## {head}\n\n{text.rstrip()}\n")
    return "\n".join(out)


def draft(p, what: str, *, origin: str = "owner", by: str | None = None, details: str | None = None,
          exc: BaseException | None = None, parts: list[str] | None = None, findings: list[str] | None = None,
          repro: str | None = None, labels: list[str] | None = None, signature: str | None = None,
          title: str | None = None, rid: str | None = None, at: float | None = None) -> dict:
    """Draft a report: scrubbed, written to ``reports/``, and recorded as an item in its first state, drafted.
    ``what``: what went wrong, in a line; ``details``: more words; ``exc``: the exception (its traceback); ``parts``: the
    parts of the model involved (a reproduction is made from them); ``findings``: the findings involved; ``repro``: a
    reproduction the agent wrote (scrubbed like the rest)."""
    what = (what or "").strip()
    if not what and exc is None:
        raise ReportError("say what went wrong: a line (ergostat report --draft \"what went wrong\")")
    if origin not in ORIGINS:
        raise ReportError(f"origin: one of {', '.join(ORIGINS)}")
    spec = getattr(getattr(p, "model", None), "spec", None)
    scrub = for_project(p, spec)
    info = about.info()
    if exc is not None and not what:
        from .trace import where
        what = f"{type(exc).__name__} in {where(exc)}"
    head = scrub.scrub(title or what).splitlines()[0] if (title or what) else "ergostat report"
    head = head if len(head) <= TITLE_MAX else head[:TITLE_MAX - 3] + "..."
    error = None
    if exc is not None:
        from .trace import pieces
        error = [("```\n", True), *pieces(exc), ("```", True)]
    shp = shape.stats(spec)
    model_path = getattr(getattr(p, "model", None), "path", None)
    rep_text, rep_note = None, None
    if repro:
        rep_text, rep_note = scrub.scrub(repro), "Written by the agent that drafted the report, scrubbed like the rest."
    else:
        rep_text = shape.repro(model_path, scrub, parts)
        if rep_text:
            rep_note = ("Generated from the model's own structure, every name a stand-in, descriptions and prompts left "
                        "out, commands made `echo 0`" + (" (the parts involved and what they name)." if parts else "."))
            if exc is not None and origin == "crash":
                rep_note += " " + _reproduces(rep_text, exc)
    sections: list[tuple[str, list[Piece] | str | None]] = [
        ("What went wrong", [(what, False)] + ([("\n\n", True), (details, False)] if details else [])),
        ("Where", f"{about.line(info)}"),
        ("Error", error),
        ("The model's shape", shape.table(shp) if shp else None),
        ("Findings involved", "\n".join(f"- {x}" for x in _findings(p, spec, findings, scrub)) or None),
        ("Reproduction", f"{rep_note}\n\n```yaml\n{rep_text.rstrip()}\n```" if rep_text else None),
    ]
    body = _body(sections, scrub)
    body += ("\n---\n_Drafted by ergostat " + {"crash": "on its own crash", "modelling": "from its modelling loop",
                                                 "agent": "for an agent", "owner": "for its owner"}[origin]
             + ". Names in the model, paths, hosts, URLs, emails, keys and the owner's denylist were replaced by stand-ins "
               "(`stock-1`, `path-2`, ...) before anyone read it._\n")
    body = scrub.seal(body)
    head = scrub.seal(head)
    labels = list(dict.fromkeys((labels or []) + LABELS.get(origin, []) + ["ergostat-report"]))
    labels = [scrub.seal(scrub.scrub(x)) for x in labels]
    rid = item_of(rid or hashlib.sha1(json.dumps([what, time.time(), uuid.uuid4().hex]).encode()).hexdigest()[:10])
    md, log_file = files(p, rid)
    folder(p)
    text = f"Title: {head}\nLabels: {', '.join(labels)}\n\n{body}"
    md.write_text(text)
    log = scrub.log()
    log_file.write_text(json.dumps({"report": rid, "removed": log, "counts": scrub.summary(),
                                    "note": "what was removed from the report, and why; kept here, never part of the text"},
                                   indent=2))
    data = {"title": head, "labels": labels, "origin": origin, "by": by or origin, "file": str(md), "scrub_file": str(log_file),
            "scrubbed": scrub.summary(), "occurrences": 1, "version": info["ergostat"], "commit": info.get("commit")}
    if signature:
        data["signature"] = signature
    ev_id = f"report-drafted-{signature}" if signature else None
    ev = p.events.add(f"{REPORT}.drafted", item=rid, source="ergostat" if origin == "crash" else (by or origin), data=data,
                      at=at, id=ev_id)
    return {"id": rid, "title": head, "labels": labels, "file": str(md), "scrub_file": str(log_file),
            "scrubbed": scrub.summary(), "recorded": ev.get("seq") is not None, "text": text}


def _reproduces(yaml_text: str, exc: BaseException) -> str:
    """Whether checking the generated model crashes the same way (a crash in ``check`` only; run in-process, offline)."""
    import tempfile

    from .trace import signature
    want = signature(exc)
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "ergostat.yaml"
        f.write_text(yaml_text)
        try:
            from ..spec import read
            read(f)
        except Exception as e:                            # noqa: BLE001  (any crash is what is looked for)
            return ("Checking it crashes the same way." if signature(e) == want
                    else "Checking it crashes, but not the same way.")
    return "Checking it does not crash: the crash needs more than this (the record, or the running engine)."


# ---- the owner's acts

def mark(p, rid: str, to: str, by: str = "owner", note: str | None = None) -> dict:
    got = get(p, rid)
    if got is None:
        raise ReportError(f"no report {rid!r} (ergostat report lists them)")
    if to not in MOVES:
        raise ReportError("a report is marked reviewed, submitted or dismissed")
    if got["state"] not in MOVES[to]:
        raise ReportError(f"{short(got['id'])} is {got['state']}: only a report {' or '.join(MOVES[to])} can be {to}")
    data = {f"{to}_by": by, **({"note": note} if note else {})}
    p.events.add(f"{REPORT}.{to}", item=got["id"], source=by, data=data)
    return get(p, got["id"])


def seen(p, rid: str) -> dict | None:
    """The same crash again: counted on its report, which stays where it is."""
    got = get(p, rid)
    if got is None:
        return None
    n = int(got.get("occurrences") or 1) + 1
    p.events.add(f"{REPORT}.seen", item=got["id"], source="ergostat", data={"occurrences": n, "last_seen": time.time()})
    return {**got, "occurrences": n}


# ---- reading them

def fold(rid: str, events: list[dict]) -> dict:
    from ..spec import items as its
    it = its.fold(item_of(rid), events, report_kind())
    return {**it.fields, "id": it.id, "state": it.state, "time": it.first, "last": it.last, "entered": it.entered,
            "moves": it.moves}


def get(p, rid: str) -> dict | None:
    evs = p.events.query(n=None, item=item_of(rid))
    if not evs:                                            # a short prefix of its id will do
        hit = {e["item"] for e in p.events.query(n=2000, type=f"{REPORT}.drafted") if short(e["item"]).startswith(short(rid))}
        if len(hit) != 1:
            return None
        evs = p.events.query(n=None, item=hit.pop())
    return fold(evs[0]["item"], evs)


def stored(p, until: float | None = None) -> dict[str, dict]:
    by: dict[str, list[dict]] = {}
    for e in p.events.query(n=None, type=f"{REPORT}.*", until=until):
        by.setdefault(e["item"], []).append(e)
    return {item: fold(item, es) for item, es in by.items() if es[0]["type"] == f"{REPORT}.drafted"}


def text_of(p, rid: str) -> dict:
    """The report as the owner reads it: the text to paste, its title and labels, the link to a new issue, and the
    scrub log (what was removed, and why)."""
    got = get(p, rid)
    if got is None:
        raise ReportError(f"no report {rid!r} (ergostat report lists them)")
    md, log_file = files(p, got["id"])
    try:
        text = md.read_text()
    except OSError:
        text = None
    try:
        log = json.loads(log_file.read_text())
    except (OSError, ValueError):
        log = {"removed": [], "counts": {}}
    body = text.split("\n\n", 1)[1] if text and text.startswith("Title: ") and "\n\n" in text else text
    return {**got, "text": text, "body": body, "issue_url": issue_url(got.get("title") or "", got.get("labels") or []),
            "removed": log.get("removed") or [], "counts": log.get("counts") or {}, "path": str(md)}


def drafted(p) -> list[dict]:
    """Reports waiting for the owner to read: each needs attention, said in one line."""
    if getattr(p, "events", None) is None:
        return []
    try:
        return [r for r in stored(p).values() if r["state"] == "drafted"]
    except Exception:
        return []
