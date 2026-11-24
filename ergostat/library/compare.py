"""An update to a fetched library reviewed before it is taken (SPEC §2a, *Before an update*): the candidate fetched by
``fetch.candidate`` (never swapped in, the lock never written), and the model compiled twice in memory under the same
flock, once on the locked copy and once on the candidate; the report is the difference. Nothing of the candidate is
written anywhere: not the running model, the last good model's snapshot, the lock or the record."""

from __future__ import annotations

import json
from pathlib import Path

from ..spec import files
from ..spec.compile import compile_doc
from ..spec.load import load, read_file
from . import fetch, fetched, sources
from . import untrusted as ut

REFS = ("unknown-ref", "bad-ref")        # a broken reference: listed first


def libraries(main: Path) -> dict:
    """The main file's ``libraries:`` read live and checked (FetchError bad-main, SourceError)."""
    problems: list = []
    data = read_file(main, problems)
    bad = [p for p in problems if p.level == "error"]
    if bad or not isinstance(data, dict):
        raise fetch.FetchError("bad-main", main.name, f"{bad[0] if bad else 'not a map of sections'}: fix it first")
    return sources.check(data.get("libraries") or {})


def update(main: Path, name: str, src: dict, version: str | None = None, say=fetch._say) -> dict:
    """The report of taking ``name`` at ``version`` (else its entry's): a version given is checked by the
    ``libraries:`` allowlist before any git process runs."""
    want = sources.check({name: {**src, "version": version}})[name] if version is not None else src
    with fetch.candidate(main.parent, name, want, say) as got:
        old = _compile(main, None)
        entry = {**{k: src[k] for k in fetch.SOURCE if k in src}, "commit": got["commit"], "tree": got["tree"]}
        new = _compile(main, {name: (got["copy"], entry)})
    return _report(name, src, want["version"], got, old, new)


def _compile(main: Path, over):
    """(doc, spec, problems) as ``spec.read`` gives them, with ``over`` standing in for the lock and copy, and no
    file read noted for a snapshot."""
    from ..spec.findings import find
    t1, t2 = fetched.OVER.set(over), files._NOW.set(None)
    try:
        doc = load(main)
        spec, problems = compile_doc(doc)
        if not any(p.level == "error" for p in problems):
            problems += find(spec, True)
    finally:
        files._NOW.reset(t2)
        fetched.OVER.reset(t1)
    return doc, spec, problems


def _plain(v):
    return json.loads(json.dumps(v, default=str))


def _report(name, src, version, got, old, new) -> dict:
    (d0, s0, p0), (d1, s1, p1) = old, new
    untrusted = src.get("trust") != "owner"
    t0, t1 = ({t.name: t for t in d.fetched if t.library == name} for d in (d0, d1))
    out = {"library": name, "version": version, "from": got["pinned"], "to": got["commit"], "tags": got["tags"],
           **({"tags_why": got["tags_why"]} if got["tags"] is None else {}),
           "templates": {"added": sorted(set(t1) - set(t0)), "removed": sorted(set(t0) - set(t1))}, "uses": []}
    marked = False

    def lib(v, t):                          # a value the library may have written
        nonlocal marked
        if not untrusted or v is None or isinstance(v, bool | int | float):
            return _plain(v)
        marked = True
        return ut.mark_all(_plain(v), ut.LABEL.format(t))

    insts = {i for d in (d0, d1) for i, u in d.uses.items() if u.get("library") == name}
    for inst in sorted(insts):
        u0, u1 = d0.uses.get(inst) or {}, d1.uses.get(inst) or {}
        tn = u1.get("template") or u0.get("template")
        a, b = (t.params if t else {} for t in (t0.get(tn), t1.get(tn)))
        e0, e1 = (set(u["exported"] if u.get("exports") is not None else u.get("parts") or ()) for u in (u0, u1))
        m0, m1 = (set(u.get("parts") or ()) | set(u.get("named") or ()) for u in (u0, u1))
        v0, v1 = u0.get("values") or {}, u1.get("values") or {}
        moved = [{"name": k, "from": lib(v0[k], tn), "to": lib(v1[k], tn)} for k in sorted(set(v0) & set(v1))
                 if v0[k] != v1[k]]
        made = set(u0.get("parameters") or ()) & set(u1.get("parameters") or ())   # the ones this use made, in both
        moved += [{"name": f"parameter.{k}", "from": s0.parameters[k].value, "to": s1.parameters[k].value}
                  for k in sorted(made & set(s0.parameters) & set(s1.parameters))
                  if s0.parameters[k].value != s1.parameters[k].value]
        out["uses"].append({
            "instance": inst, "template": tn,
            "params": {"added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)),
                       "newly_required": sorted(k for k in b if b[k].required and not (k in a and a[k].required))},
            "defaults": [{"name": k, "from": lib(a[k].default, tn), "to": lib(b[k].default, tn)}
                         for k in sorted(set(a) & set(b))
                         if (a[k].has_default, a[k].default) != (b[k].has_default, b[k].default)],
            "exports_removed": sorted(e0 - e1),
            "parts": {"added": sorted(m1 - m0), "removed": sorted(m0 - m1)}, "values": moved})
    copy, dest = str(got["copy"]), str(got["dest"])

    def key(p):                             # the same problem in both, wherever the copy sits
        return p.level, p.code, p.about, p.message.replace(copy, dest)
    seen = {key(p) for p in p0}
    fresh = sorted((p for p in p1 if key(p) not in seen),
                   key=lambda p: (p.level != "error", p.code not in REFS))
    sh = ut.Shown(s1)
    out["problems"] = [{"level": p.level, "code": p.code, "about": p.about,
                        "message": sh.problem(p).replace(copy, dest) if untrusted else p.message.replace(copy, dest),
                        "file": str(p.where.file) if p.where else None, "line": p.where.line if p.where else None}
                       for p in fresh]
    out["ok"] = not any(p.level == "error" for p in fresh)
    if marked or sh.marked:
        out["untrusted"] = ut.SAYS
    return out


def lines(r: dict) -> list[str]:
    """The report as the command line says it."""
    def j(xs):
        return ", ".join(xs) or "none"
    out = [f"library {r['library']}: dry run, nothing taken: {(r['from'] or 'not locked')[:12]} -> {r['to'][:12]} "
           f"({r['version']})",
           f"  newer tags: {j(r['tags'])}" if r["tags"] is not None else f"  newer tags: unknown ({r['tags_why']})",
           f"  templates added: {j(r['templates']['added'])}; removed: {j(r['templates']['removed'])}"]
    for u in r["uses"]:
        out.append(f"  use {u['instance']} (template {u['template']}):")
        ps = u["params"]
        out.append(f"    parameters added: {j(ps['added'])}; removed: {j(ps['removed'])}; "
                   f"newly required: {j(ps['newly_required'])}")
        out += [f"    default of {x['name']}: {x['from']!r} -> {x['to']!r}" for x in u["defaults"]]
        if u["exports_removed"]:
            out.append(f"    exports removed: {j(u['exports_removed'])}")
        out.append(f"    parts added: {j(u['parts']['added'])}; removed: {j(u['parts']['removed'])}")
        out += [f"    value moved: {x['name']}: {x['from']!r} -> {x['to']!r}" for x in u["values"]]
    for p in r["problems"]:
        at = f" ({p['file']}:{p['line']})" if p["file"] else ""
        out.append(f"  new {p['level']} {p['code']}: {p['message']}{at}")
    out.append(f"library {r['library']}: " + ("the candidate compiles with no new error" if r["ok"] else
                                              f"the candidate has {sum(p['level'] == 'error' for p in r['problems'])} "
                                              "new errors"))
    if r.get("untrusted"):
        out.append(r["untrusted"])
    return out
