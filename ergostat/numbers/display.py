"""A **display** change (``ergostat.model-change`` of kind display): one that changes dashboards (``dashboards:``, and a
projection's own ``dashboards:``) and nothing else of the model, so no dynamics and no replay (SPEC §4f). ``save``
makes one from a dashboard edited where it is drawn and accepts it at once (the owner saving is the owner accepting):
the server works out the YAML entry from the dashboard (the person saving it never writes or sees YAML to edit) and
writes it where it belongs; ``reset`` takes a saved one out again; ``keep`` makes the same change and leaves it waiting
for an Accept. ``beside`` is the guard: a change is display only when every file it edits reads, dashboards left out,
as the same data as before."""

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
        a, b = _shown(a), _shown(b)
        out += [f"{Path(f).name}: {k}" for k in sorted(set(a) | set(b), key=str) if a.get(k) != b.get(k)]
    return out


def _shown(data: dict) -> dict:
    """A file's data without what is display only: ``dashboards:``, and each projection's own ``dashboards:``."""
    out = {k: v for k, v in data.items() if k != "dashboards"}
    if isinstance(out.get("projections"), dict):
        out["projections"] = {n: {k: v for k, v in m.items() if k != "dashboards"} if isinstance(m, dict) else m
                              for n, m in out["projections"].items()}
    return out


def _panel(x) -> dict:
    from ..spec.dashboards import KINDS, PANEL_KEYS
    kind = x.get("panel") if isinstance(x, dict) else None
    if kind in KINDS and kind != "query":          # any other kind of panel: its own keys, as dashboards: declares it
        size = x.get("size") if x.get("size") in SIZES else "m"
        out = {k: v for k, v in x.items() if k in (PANEL_KEYS | KINDS[kind]) - {"size"} and v not in (None, "")}
        return {**out, "size": size + ("-tall" if x.get("tall") is True else "")}
    if not isinstance(x, dict) or not isinstance(x.get("queries"), list):
        raise pr.ProposalError("not kept: a panel is a map with its queries")
    size = x.get("size") if x.get("size") in SIZES else "m"
    out = {"panel": "query", "title": str(x.get("title") or ""), "size": size + ("-tall" if x.get("tall") is True else ""),
           "form": str(x.get("form") or "line"), "queries": x["queries"]}
    if x.get("note"):
        out["note"] = str(x["note"])
    for k in ("fit", "quiet"):
        if x.get(k) is True:
            out[k] = True
    for k in ("display", "layout"):
        if isinstance(x.get(k), dict) and x[k]:
            out[k] = x[k]
    return out


def _window(spec, v) -> str | None:
    """The window a dashboard opens with, as written (``7d``), from a draft's ``since``: its words, or seconds as the
    API answers it; None when there is none, or the record cannot hold it."""
    from ..durations import parse_duration
    if isinstance(v, int | float) and not isinstance(v, bool) and v > 0:
        v = next(f"{v / n:g}{u}" for n, u in ((86400, "d"), (3600, "h"), (60, "m"), (1, "s")) if v % n == 0 or n == 1)
    try:
        return v if isinstance(v, str) and parse_duration(v) <= spec.keep else None
    except (ValueError, OverflowError):
        return None                                   # a window the record cannot hold: the page's own, not kept


def entry(spec, draft, own: str | None = None) -> tuple[str, list[str]]:
    """The draft's name and its ``dashboards:`` entry, as lines (each panel one JSON line, which YAML reads as written).
    ``own``: a projection's own dashboard of that role (``list``, ``show``), its entry named so, with no ``nav:`` or
    ``page:`` (drawn at the projection's addresses) and its title only if it has one."""
    if not isinstance(draft, dict) or not isinstance(draft.get("panels"), list) or not draft["panels"]:
        raise pr.ProposalError("not kept: a draft is {title, panels: [...]}, with a panel at least")
    if draft.get("rows") or draft.get("vars") or any(isinstance(x, dict) and x.get("repeat") for x in draft["panels"]):
        raise pr.ProposalError("not kept: rows, variables and repeated panels stay in the draft (dashboards: holds "
                               "panels alone so far)")
    title = str(draft.get("title") or ("" if own or draft.get("page") else "Dashboard"))[:200]   # a page's: its thing's name
    name = own or str(draft.get("name") or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "dashboard")[:64].strip("-")
    declared = name in (getattr(spec, "dashboards", None) or {})    # one already there: by its name (a system's: S.NAME)
    if not own and not declared and (not NAME.match(name) or name == "default"):
        raise pr.ProposalError(f"not kept: {name!r} is not a dashboard's name (lowercase letters, digits and -, "
                               "starting with a letter; not default)")
    body: dict = {"title": title} if title else {}
    if isinstance(draft.get("description"), str) and draft["description"].strip():
        body["description"] = draft["description"].strip()[:2000]
    for k in () if own else ("nav", "page"):          # in the navigation; in place of one of the page's own pages
        if draft.get(k) not in (None, "", False):
            body[k] = draft[k]
    if (window := _window(spec, draft.get("since"))) is not None:
        body["window"] = window
    panels = [_panel(x) for x in draft["panels"]]
    lines = [f"  {name}:", *(f"    {k}: {json.dumps(v)}" for k, v in body.items()), "    panels:",
             *(f"      - {json.dumps(x, sort_keys=True)}" for x in panels)]
    if yaml.safe_load("\n".join(lines)) != {name: {**body, "panels": panels}}:
        raise pr.ProposalError("not kept: the draft does not read back as YAML the same")
    return name, lines


def target_of(spec, draft) -> tuple:
    """Where a dashboard is saved: ``("projection", P, ROLE)`` for a projection's own list or show (asked for as
    ``{projection: P, role: list|show}``, or by its name P.ROLE), else ``("dashboard", NAME)``."""
    from ..spec.dashboards import PROJECTION_DASHBOARDS
    d = draft if isinstance(draft, dict) else {}
    old = spec.dashboards.get(str(d.get("name") or ""))
    if old is not None and old.projection:
        return ("projection", old.projection, old.role)
    if d.get("projection") is not None or d.get("role") is not None:
        if d.get("role") not in PROJECTION_DASHBOARDS or d.get("projection") not in spec.items or \
                getattr(spec.items[d["projection"]], "where", None) is None:
            raise pr.ProposalError(f"not kept: a projection's own dashboard is {{projection: P, role: "
                                   f"{' or '.join(PROJECTION_DASHBOARDS)}}}, P a projection the model declares")
        return ("projection", d["projection"], d["role"])
    return ("dashboard", None)


def _children(ls: list[str], at: int, lines: list[str]) -> list[str]:
    """An entry's lines (``entry``'s, its name first) put in place of the one named on line ``at``: its own name line
    kept as written (a system's file names it without the system), its keys at that line's children's indentation."""
    head = ls[at - 1]
    if re.search(r":\s*\{", head):
        raise ye.EditError(f"line {at}: the dashboard is written on one line ({{...}}); write it out a key a line first")
    pad = " " * ye.indent(head)
    return [head.split("#")[0].rstrip(), *(pad + x[2:] for x in lines[1:])]


def _projection_line(spec, name: str) -> tuple[Path, int]:
    """The file a projection is defined in, and the line naming it."""
    k = spec.items[name]
    ye.own(k.where, f"projection {name}")
    f = Path(k.where.file)
    at = ye.name_line(f, k.where.line, name)
    if re.search(r":\s*\{", ye.lines_of(f)[at - 1]):
        raise ye.EditError(f"{f.name}:{at}: projection {name} is written on one line ({{...}}); write it out a key a "
                           "line first")
    return f, at


def system_of(spec, draft) -> str:
    """The system a dashboard is saved for (``system:`` of the draft: the system whose address it is drawn at), ""
    the top level."""
    s = draft.get("system") if isinstance(draft, dict) else None
    if s in (None, ""):
        return ""
    from ..spec.scope import scope
    if not isinstance(s, str) or s not in scope(spec):
        raise pr.ProposalError(f"not kept: {s!r} is not a system of the model")
    return s


def _defaults_system(f: Path) -> str | None:
    try:
        data = yaml.safe_load("\n".join(ye.lines_of(f))) or {}
    except (yaml.YAMLError, OSError):
        return None
    d = data.get("defaults") if isinstance(data, dict) else None
    return d.get("system") if isinstance(d, dict) else None


def system_file(spec, system: str) -> Path | None:
    """The file a system's own things are written in (its ``defaults: system:`` is the system): where its dashboards
    are saved. None: the model has none, so a dashboard of it is written in the main file with ``system:``."""
    tables = (spec.dashboards, spec.stocks, spec.flows, spec.goals, spec.items, spec.blocks, spec.auxiliaries,
              spec.agents, spec.parameters)
    files = dict.fromkeys(Path(w.file) for t in tables for x in t.values()
                          if (w := getattr(x, "where", None)) is not None and getattr(w, "file", None))
    return next((f for f in files if _defaults_system(f) == system), None)


def _with_system(lines: list[str], system: str, f: Path) -> list[str]:
    """A system's dashboard entry, with ``system:`` when the file it is written in is not that system's own."""
    if not system or _defaults_system(f) == system:
        return lines
    return [lines[0], f"    system: {json.dumps(system)}", *lines[1:]]


def _edit(p, spec, target: tuple, lines: list[str], system: str = "") -> ye.Edit:
    """The entry added under ``dashboards:`` (or, a projection's own, under the projection's ``dashboards:`` in the
    file it is defined in; a system's, in the system's own file, else the main file with ``system:``), or put in
    place of the one declared there."""
    if target[0] == "projection":
        _, name, role = target
        old = spec.dashboards.get(f"{name}.{role}")
        if old is not None and old.where is not None:
            f, at = Path(old.where.file), old.where.line
            ls = ye.lines_of(f)
            end, _ = ye.children(ls, at)
            return ye.Edit(str(f), [ye.Hunk(at, ls[at - 1:end], _children(ls, at, lines))])
        f, at = _projection_line(spec, name)
        ls = ye.lines_of(f)
        own = ye.key_line(ls, at, "dashboards")
        body = [x[2:] for x in lines]                  # role: then its keys, one level in
        if own is None:
            return ye.set_key(f, at, "dashboards", body)
        return ye.set_key(f, own, role, [x[2:] for x in body[1:]])
    full = target[1] or lines[0].strip().rstrip(":")
    old = spec.dashboards.get(full)
    if old is None or old.where is None:
        f = (system_file(spec, system) if system else None) or Path(p.model.path)
        return ye.add_entries(f, "dashboards", [_with_system(lines, system, f)])
    f, at = Path(old.where.file), old.where.line
    ls = ye.lines_of(f)
    end, _ = ye.children(ls, at)
    return ye.Edit(str(f), [ye.Hunk(at, ls[at - 1:end], _children(ls, at, _with_system(lines, old.system or "", f)))])


def _removal(p, spec, target: tuple) -> tuple[str, ye.Edit]:
    """The saved dashboard taken out of the YAML (with the ``dashboards:`` it leaves empty): ergostat's own is drawn
    in its place again."""
    full = f"{target[1]}.{target[2]}" if target[0] == "projection" else target[1]
    old = spec.dashboards.get(full)
    if old is None or old.where is None:
        raise pr.ProposalError(f"not reset: no dashboard {full} is saved in the model")
    f, at = Path(old.where.file), old.where.line
    ls = ye.lines_of(f)
    end, _ = ye.children(ls, at)
    if target[0] == "projection":
        _, pat = _projection_line(spec, target[1])
        holder = ye.key_line(ls, pat, "dashboards")
    else:
        holder = next((i for i in range(at - 1, 0, -1) if re.match(r"^dashboards\s*:\s*(#.*)?$", ls[i - 1])), None)
    if holder is not None:
        hend, _ = ye.children(ls, holder)
        said = lambda xs: [x for x in xs if x.strip() and not x.strip().startswith("#")]   # noqa: E731
        if len(said(ls[holder:hend])) == len(said(ls[at - 1:end])):
            return full, ye.Edit(str(f), [ye.Hunk(holder, ls[holder - 1:hend], [])])     # it was the only one
    return full, ye.Edit(str(f), [ye.Hunk(at, ls[at - 1:end], [])])


def _change(p, spec, target: tuple, edit: ye.Edit, title: str, made_by: str, scope: str, words: str,
            model: bool = False) -> dict:
    """The edit as one display change made by ``made_by``, waiting for Accept. Refused (``ProposalError``) when the
    model it leaves does not pass ``check``, or when it would change anything but dashboards. ``model``: a
    projection's definition (``save_projection``), a change to the model itself, of the kind it is."""
    from .improve import finding_id, kind_of
    try:
        texts = tr.texts_after([edit])
    except (ye.EditError, tr.TrialError) as e:
        raise pr.ProposalError(f"not kept: {e}") from None
    after, problems = tr.compiled(p.model.path, texts, findings=True)
    errors = [str(x) for x in problems if x.level == "error"]
    if errors:
        raise pr.ProposalError("not kept: the dashboard it declares does not pass check: " + "; ".join(errors[:3]))
    if model:
        kind = kind_of(spec, after, "structure")
    else:
        bad = beside(texts)
        if bad or kind_of(spec, after, "display") != "display":
            raise pr.ProposalError("not a display change: " + (f"it changes {', '.join(bad)}" if bad else
                                   "it changes nothing of dashboards: (kept as it is already)"))
        kind = "display"
    _, was = tr.compiled(p.model.path, {}, findings=True)
    seen = {finding_id(x.code, x.about) for x in was if x.level != "error"}
    new = sorted({finding_id(x.code, x.about) for x in problems if x.level != "error"} - seen)
    v = ver.version(spec)
    full = f"{target[1]}.{target[2]}" if target[0] == "projection" else target[1]
    x = {"kind": kind, "made_by": made_by, "scope": scope, "scope_words": words,
         "title": title, "target": f"projection.{full}" if model else f"dashboard.{full}",
         "parts": [f"projection.{full}"] if model else [], "touched": [],
         "reason": "a projection defined where its items are drawn, tried on the record before it was saved" if model
         else "a dashboard changed where it is drawn: it changes dashboards alone (no dynamics, no replay)",
         "change": "a projection's definition: how the record's events fold into its items" if model
         else "a dashboard declared: what the page shows",
         "findings": {"answered": [], "new": new, "notes_answered": [], "notes_new": []},
         "edit": pr._joined([edit]), "status": "pending", "created": time.time(), "structure": ver.structure(spec), "version": v}
    hunks = [y for h in edit.hunks for y in (*h.old, "->", *h.new)]
    with pr.locked(p):                                 # read again under the lock: the judge records here too
        props = pr.stored(p)
        pid = pr._id(kind, full, v, hunks)
        if (props.get(pid) or {}).get("status") not in (None, "pending"):
            pid = pr._id(kind, full, v, hunks, time.time())          # kept again after it was decided: a new change
        props[pid] = x = {**x, "id": pid}
        pr.save(p, props)
    return x


def _made(p, spec, draft) -> tuple[tuple, ye.Edit]:
    target = target_of(spec, draft)
    system = ""
    if target[0] == "dashboard":                   # a system's: named SYSTEM.NAME, its entry NAME in its file
        system = system_of(spec, draft)
        local = str(draft.get("name") or "")
        if system and local.startswith(system + "."):
            local = local[len(system) + 1:]
        draft = {**draft, "name": local} if local else draft
    name, lines = entry(spec, draft, own=target[2] if target[0] == "projection" else None)
    if target[0] == "dashboard":
        full = f"{system}.{name}" if system else name
        target = ("dashboard", full)
        if draft.get("new") and full in spec.dashboards:
            raise pr.ProposalError(f"not saved: a dashboard named {full} is in the model already; name this one otherwise")
    try:
        return target, _edit(p, spec, target, lines, system)
    except ye.EditError as e:
        raise pr.ProposalError(f"not kept: {e}") from None


def keep(p, draft) -> dict:
    """The owner's Keep: the draft made one display change, made by the owner, waiting for their Accept. Refused
    (``ProposalError``) when the model it leaves does not pass ``check``, or when it would change anything but
    dashboards."""
    spec = p.model.spec
    target, edit = _made(p, spec, draft)
    full = f"{target[1]}.{target[2]}" if target[0] == "projection" else target[1]
    return _change(p, spec, target, edit, f"Keep the dashboard {full}", "owner", "keep",
                   "the owner's Keep, of a dashboard drawn on the page")


def save(p, draft, snap: dict, by: str = "owner") -> dict:
    """The owner's Save, where the dashboard is drawn: written at once. The same display change as ``keep`` (the same
    checks: it must pass ``check`` and change nothing but dashboards), made by whoever saves and accepted by them in
    the same step, as Accept writes any change (``proposals.accept``)."""
    spec = p.model.spec
    target, edit = _made(p, spec, draft)
    full = f"{target[1]}.{target[2]}" if target[0] == "projection" else target[1]
    x = _change(p, spec, target, edit, f"Save the dashboard {full}", by, "save", "saved where it is drawn, on the page")
    return {**pr.accept(p, x["id"], snap, by=by), "dashboard": full}


def reset(p, draft, snap: dict, by: str = "owner") -> dict:
    """The saved dashboard taken out of the YAML, so ergostat's own is drawn in its place again: a display change made
    and accepted at once, as ``save``."""
    spec = p.model.spec
    d = draft if isinstance(draft, dict) else {}
    target = target_of(spec, d)
    if target[0] == "dashboard":
        system, name = system_of(spec, d), str(d.get("name") or "")
        target = ("dashboard", f"{system}.{name}" if system and not name.startswith(system + ".") else name)
    try:
        full, edit = _removal(p, spec, target)
    except ye.EditError as e:
        raise pr.ProposalError(f"not reset: {e}") from None
    x = _change(p, spec, target, edit, f"Reset the dashboard {full} to ergostat's", by, "save",
                "reset where it is drawn, on the page")
    return {**pr.accept(p, x["id"], snap, by=by), "dashboard": full}


def save_projection(p, draft, snap: dict, by: str = "owner") -> dict:
    """The owner's Save of a projection's definition from its own page (``{name, yaml, system?, new?}``: the YAML its
    body, as the page's Definition editor holds it), put in place of the projection (its ``dashboards:`` kept) or, a
    new one, at the end of ``projections:`` in its system's file (else the main file). Not a display change: a change
    to the model, made by the owner and accepted in the same step, as Accept writes any (``proposals.accept``);
    refused when the model it leaves does not pass ``check``."""
    from ..spec import trying
    d = draft if isinstance(draft, dict) else {}
    name, text = str(d.get("name") or ""), d.get("yaml")
    if not isinstance(text, str):
        raise pr.ProposalError("not saved: {name, yaml}: the projection's name and its body as YAML")
    spec = p.model.spec
    system = system_of(spec, d) if d.get("system") else ""
    if d.get("new") and name in spec.items:
        raise pr.ProposalError(f"not saved: a projection named {name} is in the model already; name this one otherwise")
    try:
        _, edit, errors = trying.compiled(p, name, text, system)
    except trying.TryError as e:
        raise pr.ProposalError(f"not saved: {e}") from None
    if errors:
        raise pr.ProposalError("not saved: it does not pass check: " + "; ".join(
            (f"line {e['line']}: " if e.get("line") else "") + e["message"] for e in errors[:3]))
    x = _change(p, spec, ("dashboard", name), edit, f"Save the projection {name}", by, "save",
                "saved where its items are drawn, on the page", model=True)
    return {**pr.accept(p, x["id"], snap, by=by), "projection": name}
