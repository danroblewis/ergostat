"""A **display** change (``ergostat.model-change`` of kind display): one that changes ``dashboards:`` and nothing else
of the model, so no dynamics and no replay (SPEC §4f). ``keep`` makes one from a draft kept on the Dashboard page:
the server works out the ``dashboards:`` entry from the draft (the person keeping it never writes or sees YAML to
edit), and it waits for the owner's Accept like any proposal. ``beside`` is the guard: a change is display only when
every file it edits reads, ``dashboards:`` left out, as the same data as before."""

from __future__ import annotations

import dataclasses
import json
import re
import time
from pathlib import Path

import yaml

from . import proposals as pr
from . import trial as tr
from . import version as ver
from . import yamledit as ye

NAME = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
SIZES = ("s", "m", "l", "full")


def display_only(before, after) -> bool:
    """Whether ``dashboards:`` changed and nothing else of the compiled model did (every other field, the words too)."""
    if ver._plain(before.dashboards) == ver._plain(after.dashboards):
        return False
    return ver.words(before) == ver.words(after) and all(
        ver._plain(getattr(before, f.name)) == ver._plain(getattr(after, f.name))
        for f in dataclasses.fields(before) if f.name != "dashboards")


def beside(texts: dict[str, str]) -> list[str]:
    """What the new ``texts`` change besides ``dashboards:``: each file's top-level keys whose data differs (a file
    that cannot be read, before or after, counts as changed whole)."""
    out = []
    for f, new in texts.items():
        try:
            a = yaml.safe_load("\n".join(ye.lines_of(Path(f)))) or {}
            b = yaml.safe_load(new) or {}
        except (yaml.YAMLError, OSError):
            out.append(f"{Path(f).name}: it cannot be read")
            continue
        if not isinstance(a, dict) or not isinstance(b, dict):
            out.append(f"{Path(f).name}: not a map")
            continue
        out += [f"{Path(f).name}: {k}" for k in sorted(set(a) | set(b), key=str) if k != "dashboards" and a.get(k) != b.get(k)]
    return out


def _panel(x) -> dict:
    if not isinstance(x, dict) or not isinstance(x.get("queries"), list):
        raise pr.ProposalError("not kept: a panel is a map with its queries")
    size = x.get("size") if x.get("size") in SIZES else "m"
    out = {"panel": "query", "title": str(x.get("title") or ""), "size": size + ("-tall" if x.get("tall") is True else ""),
           "form": str(x.get("form") or "line"), "queries": x["queries"]}
    if x.get("note"):
        out["note"] = str(x["note"])
    for k in ("display", "layout"):
        if isinstance(x.get(k), dict) and x[k]:
            out[k] = x[k]
    return out


def entry(spec, draft) -> tuple[str, list[str]]:
    """The draft's name and its ``dashboards:`` entry, as lines (each panel one JSON line, which YAML reads as written)."""
    if not isinstance(draft, dict) or not isinstance(draft.get("panels"), list) or not draft["panels"]:
        raise pr.ProposalError("not kept: a draft is {title, panels: [...]}, with a panel at least")
    if draft.get("rows") or draft.get("vars") or any(isinstance(x, dict) and x.get("repeat") for x in draft["panels"]):
        raise pr.ProposalError("not kept: rows, variables and repeated panels stay in the draft (dashboards: holds "
                               "panels alone so far)")
    title = str(draft.get("title") or "Dashboard")[:200]
    name = str(draft.get("name") or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "dashboard")[:64].strip("-")
    if not NAME.match(name) or name == "default":
        raise pr.ProposalError(f"not kept: {name!r} is not a dashboard's name (lowercase letters, digits and -, "
                               "starting with a letter; not default)")
    body: dict = {"title": title}
    try:
        from ..durations import parse_duration
        if isinstance(draft.get("since"), str) and parse_duration(draft["since"]) <= spec.keep:
            body["window"] = draft["since"]
    except (ValueError, OverflowError):
        pass                                          # a window the record cannot hold: the page's own, not kept
    panels = [_panel(x) for x in draft["panels"]]
    lines = [f"  {name}:", *(f"    {k}: {json.dumps(v)}" for k, v in body.items()), "    panels:",
             *(f"      - {json.dumps(x, sort_keys=True)}" for x in panels)]
    if yaml.safe_load("\n".join(lines)) != {name: {**body, "panels": panels}}:
        raise pr.ProposalError("not kept: the draft does not read back as YAML the same")
    return name, lines


def _edit(p, spec, name: str, lines: list[str]) -> ye.Edit:
    """The entry added under ``dashboards:``, or put in place of the one declared under that name."""
    old = spec.dashboards.get(name)
    if old is None or old.where is None:
        return ye.add_entries(p.model.path, "dashboards", [lines])
    f, at = Path(old.where.file), old.where.line
    ls = ye.lines_of(f)
    end, _ = ye.children(ls, at)
    pad = " " * (ye.indent(ls[at - 1]) - 2)
    return ye.Edit(str(f), [ye.Hunk(at, ls[at - 1:end], [pad + x for x in lines])])


def keep(p, draft) -> dict:
    """The owner's Keep: the draft made one display change, made by the owner, waiting for their Accept. Refused
    (``ProposalError``) when the model it leaves does not pass ``check``, or when it would change anything but
    ``dashboards:``."""
    from .improve import finding_id, kind_of
    spec = p.model.spec
    name, lines = entry(spec, draft)
    try:
        edit = _edit(p, spec, name, lines)
        texts = tr.texts_after([edit])
    except (ye.EditError, tr.TrialError) as e:
        raise pr.ProposalError(f"not kept: {e}") from None
    after, problems = tr.compiled(p.model.path, texts, findings=True)
    errors = [str(x) for x in problems if x.level == "error"]
    if errors:
        raise pr.ProposalError("not kept: the dashboard it declares does not pass check: " + "; ".join(errors[:3]))
    bad = beside(texts)
    if bad or kind_of(spec, after, "display") != "display":
        raise pr.ProposalError("not a display change: " + (f"it changes {', '.join(bad)}" if bad else
                               "it changes nothing of dashboards: (kept as it is already)"))
    _, was = tr.compiled(p.model.path, {}, findings=True)
    seen = {finding_id(x.code, x.about) for x in was if x.level != "error"}
    new = sorted({finding_id(x.code, x.about) for x in problems if x.level != "error"} - seen)
    v = ver.version(spec)
    x = {"kind": "display", "made_by": "owner", "scope": "keep", "scope_words": "the owner's Keep, on the Dashboard page",
         "title": f"Keep the dashboard {name}", "target": f"dashboard.{name}", "parts": [], "touched": [],
         "reason": "a draft the owner kept on the Dashboard page: it changes dashboards: alone (no dynamics, no replay)",
         "change": "a dashboard declared: what the Dashboard page shows",
         "findings": {"answered": [], "new": new, "notes_answered": [], "notes_new": []},
         "edit": pr._joined([edit]), "status": "pending", "created": time.time(), "structure": ver.structure(spec), "version": v}
    with pr.locked(p):                                 # read again under the lock: the judge records here too
        props = pr.stored(p)
        pid = pr._id("display", name, v, lines)
        if (props.get(pid) or {}).get("status") not in (None, "pending"):
            pid = pr._id("display", name, v, lines, time.time())     # kept again after it was decided: a new change
        props[pid] = x = {**x, "id": pid}
        pr.save(p, props)
    return x
