"""Which system each item kind belongs to, for the Items page's groups: worked out from what the
model already says, never declared for the purpose.

In order:

1. **declared**: the kind's own ``system:``, or the ``defaults: system:`` of the file it is declared
   in. Where the model declares a kind wins over where it is counted.
2. **built in**: ergostat's own kinds (``ergostat.*``) are in ``ergostat``, wherever they are counted.
3. **counted**: the systems of the stocks, flows and auxiliaries whose ``items:`` sensors count the
   kind. One system: that one. Several: the innermost system they are all within (intake and
   delivery, both within the factory: the factory); none shared: the one counting it most, the
   first declared on a tie.
4. **other**: nothing says.
"""

from __future__ import annotations

BUILT_IN = "ergostat"
OTHER = "other"


def kind_systems(spec) -> dict[str, dict]:
    """Each kind → ``{"system": name, "why": how it was decided}``."""
    kinds = getattr(spec, "items", None) or {}
    if not kinds:
        return {}
    counted: dict[str, list[str]] = {}                 # kind → the system of each part counting it
    for s in spec.sensors():
        if s.items and (sys_ := spec.owner(s.of)):
            counted.setdefault(s.items.get("kind"), []).append(sys_)
    out = {}
    for name, k in kinds.items():
        if k.system:
            out[name] = {"system": k.system, "why": "declared"}
        elif name.startswith(BUILT_IN + "."):
            out[name] = {"system": BUILT_IN, "why": "built in"}
        elif name in counted:
            out[name] = _counted(spec, counted[name])
        else:
            out[name] = {"system": OTHER, "why": "nothing says"}
    return out


def _counted(spec, systems: list[str]) -> dict:
    order = list(spec.systems)
    rank = lambda s: order.index(s) if s in order else len(order)     # noqa: E731
    seen = sorted(set(systems), key=rank)                             # in the order the model declares them
    if len(seen) == 1:
        return {"system": seen[0], "why": f"counted in {seen[0]}"}
    said = ", ".join(seen)
    chains = [spec.chain(s) for s in seen]
    shared = next((s for s in chains[0] if all(s in c for c in chains[1:])), None)
    if shared:
        return {"system": shared, "why": f"counted in {said}: all within {shared}"}
    most = max(seen, key=lambda s: (systems.count(s), -rank(s)))
    return {"system": most, "why": f"counted in {said}: most in {most}"}


def groups(spec, kind_system: dict[str, dict]) -> list[dict]:
    """The systems that hold a kind, in the model's order (each after the system it is within), then
    ergostat's own, then other: each with its description and its kinds, in their declared order."""
    by: dict[str, list[str]] = {}
    for kind, x in kind_system.items():
        by.setdefault(x["system"], []).append(kind)
    systems = dict(getattr(spec, "systems", None) or {})
    within = getattr(spec, "within", None) or {}
    order: list[str] = []

    def walk(parent):
        for s in systems:
            if within.get(s) == parent and s not in order:
                order.append(s)
                walk(s)
    walk(None)
    order += [s for s in systems if s not in order]               # a cycle the check refused: still listed
    order += [s for s in by if s not in order]                    # named by a kind, not described
    order = [s for s in dict.fromkeys(order) if s not in (BUILT_IN, OTHER)] + [BUILT_IN, OTHER]
    return [{"name": s, "description": systems.get(s, ""), "kinds": by[s]} for s in order if s in by]
