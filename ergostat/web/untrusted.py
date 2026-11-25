"""What an untrusted template made, marked on the graph's answer (SPEC §2a), for the page to say so in words."""

from __future__ import annotations


def untrusted(g: dict, model) -> None:
    """Each drawn part and closed system box an untrusted template made (``untrusted.Shown``, SPEC §2a): its node's
    ``untrusted``, the template's name escaped ("" when none is known), for the page to say so in words. A shape is
    the part it stands for first (``corr``), never a region it holds; a system box, its system."""
    from ..library.untrusted import Shown, escape
    spec = getattr(model, "spec", None)
    if spec is None or not isinstance(g.get("nodes"), list):
        return
    sh, shapes = Shown(spec), (g.get("corr") or {}).get("shapes") or {}
    for n in g["nodes"]:
        x = shapes.get(n.get("id")) or {}
        if x.get("system"):
            name, u = x["system"] in sh.systems, sh.uses.get(x["system"])
            t = u.get("template") if isinstance(u, dict) else None
        else:
            part = sh.parts.get(".".join((x.get("is") or [""])[0].split(".")[:2])) if not x.get("region") else None
            name, t = (part, getattr(part[1].where, "template", None)) if part else (None, None)
        if name:
            n["untrusted"] = escape(t) if isinstance(t, str) else ""
