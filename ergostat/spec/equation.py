"""Equations (SPEC §7b): what a flow's rate or an auxiliary's value is, written in the model's own
names, the way Vensim and Stella write them.

    alerts-base + alerts-per-ramp * stock.unreviewed-ramps-live
    (auxiliary.batch-quality - stock.quality) / window-time
    DELAY1(flow.ramps-went-ahead, time-to-break)

A bare name is a parameter (``parameters:``); a part is a reference (``stock.x``, ``flow.x``,
``auxiliary.x``). Names have hyphens in them, so subtraction is written with spaces: ``a - b``.
Functions: MIN, MAX, ABS, EXP, LN, SQRT, ZIDZ(a, b) and XIDZ(a, b, x) (a / b, or 0, or x, where b is 0:
Vensim's, for a division by 0 that is meant), and system dynamics' delays, DELAY1 and DELAY3 (a
material delay of the first or third order: what goes in comes out after the delay time, on
average) and SMOOTH and SMOOTH3 (an information delay: exponential smoothing); a parameter with a
``table:`` is a lookup, called like a function (``effect-of-load(stock.queue)``).

Parsed into a small tree of tuples; compiled into closures for the simulator; its units worked out
from the units written on what it names; and given to the page as a tree it draws in MathML."""

from __future__ import annotations

import math
import re
from fractions import Fraction

FUNCS = {"MIN": (2, None), "MAX": (2, None), "ABS": (1, 1), "EXP": (1, 1), "LN": (1, 1), "SQRT": (1, 1),
         "ZIDZ": (2, 2), "XIDZ": (3, 3), "DELAY1": (2, 2), "DELAY3": (2, 2), "SMOOTH": (2, 2), "SMOOTH3": (2, 2)}
DELAYS = {"DELAY1": 1, "DELAY3": 3, "SMOOTH": 1, "SMOOTH3": 3}     # each keeps this many hidden stocks
TOKEN = re.compile(r"""\s*(?:
    (?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
  | (?P<ref>(?:stock|flow|auxiliary)\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)
  | (?P<name>[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)*)
  | (?P<op>\*\*|[-+*/^(),])
)""", re.X)


class EquationError(Exception):
    pass


# ---- reading

def tokens(text: str) -> list[tuple[str, str]]:
    out, at = [], 0
    text = text.rstrip()
    while at < len(text):
        m = TOKEN.match(text, at)
        if m is None or m.end() == at:
            raise EquationError(f"cannot read {text[at:].strip()[:20]!r}")
        kind = m.lastgroup
        out.append((kind, "^" if m.group(kind) == "**" else m.group(kind)))
        at = m.end()
    return out


def parse(text: str, parameters: dict | None = None) -> tuple:
    """The tree of an equation. ``parameters`` (name → anything with a ``table``) tells a lookup's
    call from an unknown function. Names are checked later, by the compiler."""
    if not isinstance(text, str) or not text.strip():
        raise EquationError("an equation: an expression of parameters and parts, like base + k * stock.x")
    toks = tokens(text)
    pos = [0]
    tables = {n for n, p in (parameters or {}).items() if getattr(p, "table", None)}

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else (None, None)

    def take(want=None):
        t = peek()
        if t[0] is None or (want and t[1] != want):
            raise EquationError(f"expected {want!r}" + (f", found {t[1]!r}" if t[1] else " at the end"))
        pos[0] += 1
        return t

    def additive():
        node = multiplicative()
        while peek()[1] in ("+", "-"):
            op = take()[1]
            node = ("bin", op, node, multiplicative())
        return node

    def multiplicative():
        node = unary()
        while peek()[1] in ("*", "/"):
            op = take()[1]
            node = ("bin", op, node, unary())
        return node

    def unary():
        if peek()[1] == "-":
            take()
            return ("neg", unary())
        if peek()[1] == "+":
            take()
            return unary()
        return power()

    def power():
        base = primary()
        if peek()[1] == "^":
            take()
            return ("bin", "^", base, unary())          # right-associative, and binds tighter than a minus before it
        return base

    def primary():
        kind, val = peek()
        if kind == "num":
            take()
            return ("num", float(val))
        if kind == "ref":
            take()
            k, _, n = val.partition(".")
            return ("ref", k, n)
        if kind == "name":
            take()
            if peek()[1] == "(":
                take("(")
                args = [additive()]
                while peek()[1] == ",":
                    take(",")
                    args.append(additive())
                take(")")
                up = val.upper()
                if val in tables:
                    if len(args) != 1:
                        raise EquationError(f"{val} is a lookup: it takes one input, {val}(x)")
                    return ("lookup", val, args[0])
                if up not in FUNCS:
                    raise EquationError(f"{val}() is not a function: {', '.join(FUNCS)}, or a parameter with a table:")
                least, most = FUNCS[up]
                if len(args) < least or (most is not None and len(args) > most):
                    raise EquationError(f"{up} takes {least if least == most else f'{least} or more'} input"
                                        f"{'s' if (most or 2) > 1 else ''}")
                return ("fn", up, args)
            return ("par", val)
        if val == "(":
            take("(")
            node = additive()
            take(")")
            return node
        raise EquationError("expected a number, a name or a part" + (f", found {val!r}" if val else " at the end"))

    tree = additive()
    if pos[0] != len(toks):
        raise EquationError(f"unexpected {toks[pos[0]][1]!r}")
    return tree


def walk(tree):
    yield tree
    tag = tree[0]
    if tag == "neg":
        yield from walk(tree[1])
    elif tag == "bin":
        yield from walk(tree[2])
        yield from walk(tree[3])
    elif tag == "fn":
        for a in tree[2]:
            yield from walk(a)
    elif tag == "lookup":
        yield from walk(tree[2])


def refs(tree) -> list[str]:
    """The parts it names (``stock.x``), in order, once each."""
    out: list[str] = []
    for n in walk(tree):
        if n[0] == "ref" and f"{n[1]}.{n[2]}" not in out:
            out.append(f"{n[1]}.{n[2]}")
    return out


def instant_refs(tree) -> list[str]:
    """The parts it names outside a delay's input: those it depends on at once (a delay's input is
    taken in now and comes out later, so it orders nothing)."""
    out: list[str] = []

    def go(n, held):
        tag = n[0]
        if tag == "ref" and not held and f"{n[1]}.{n[2]}" not in out:
            out.append(f"{n[1]}.{n[2]}")
        elif tag == "neg":
            go(n[1], held)
        elif tag == "bin":
            go(n[2], held)
            go(n[3], held)
        elif tag == "fn":
            for i, a in enumerate(n[2]):
                go(a, held or (n[1] in DELAYS and i == 0))
        elif tag == "lookup":
            go(n[2], held)
    go(tree, False)
    return out


def delayed_refs(tree, material: bool = False) -> list[str]:
    """The parts it names only inside a delay's input (only a material one, DELAY1 or DELAY3, with
    ``material``): what reaches it through the delay's own stocks, never at once."""
    inside: list[str] = []

    def go(n, held):
        tag = n[0]
        if tag == "ref" and held and f"{n[1]}.{n[2]}" not in inside:
            inside.append(f"{n[1]}.{n[2]}")
        elif tag == "neg":
            go(n[1], held)
        elif tag == "bin":
            go(n[2], held)
            go(n[3], held)
        elif tag == "fn":
            for i, a in enumerate(n[2]):
                go(a, held or (n[1] in DELAYS and i == 0 and (not material or n[1].startswith("DELAY"))))
        elif tag == "lookup":
            go(n[2], held)
    go(tree, False)
    now = set(instant_refs(tree))
    return [r for r in inside if r not in now]


def names(tree) -> list[str]:
    """The parameters it names (a lookup's table among them)."""
    out: list[str] = []
    for n in walk(tree):
        nm = n[1] if n[0] in ("par", "lookup") else None
        if nm and nm not in out:
            out.append(nm)
    return out


def text(tree) -> str:
    """The tree written back, with as few brackets as it needs."""
    prec = {"+": 1, "-": 1, "*": 2, "/": 2, "^": 4}

    def go(n, outer=0, right=False):
        tag = n[0]
        if tag == "num":
            v = n[1]
            return str(int(v)) if v == int(v) and abs(v) < 1e15 else f"{v:.6g}"
        if tag == "par":
            return n[1]
        if tag == "ref":
            return f"{n[1]}.{n[2]}"
        if tag == "neg":
            s = "-" + go(n[1], 3)
            return f"({s})" if outer > 3 else s
        if tag == "bin":
            p = prec[n[1]]
            s = f"{go(n[2], p)} {n[1]} {go(n[3], p, True)}" if n[1] != "^" else f"{go(n[2], 5)}^{go(n[3], 4)}"
            need = outer > p or (right and outer == p and n[1] in "+-*/")
            return f"({s})" if need else s
        if tag == "fn":
            return f"{n[1]}({', '.join(go(a) for a in n[2])})"
        if tag == "lookup":
            return f"{n[1]}({go(n[2])})"
        raise EquationError(tag)
    return go(tree)


# ---- the page's tree: drawn as MathML (static/equations.js)

def tree_json(tree) -> dict:
    tag = tree[0]
    if tag == "num":
        return {"num": tree[1]}
    if tag == "par":
        return {"par": tree[1]}
    if tag == "ref":
        return {"ref": f"{tree[1]}.{tree[2]}", "kind": tree[1], "name": tree[2]}
    if tag == "neg":
        return {"op": "neg", "args": [tree_json(tree[1])]}
    if tag == "bin":
        return {"op": tree[1], "args": [tree_json(tree[2]), tree_json(tree[3])]}
    if tag == "fn":
        return {"fn": tree[1], "args": [tree_json(a) for a in tree[2]]}
    return {"fn": tree[1], "lookup": True, "args": [tree_json(tree[2])]}


# ---- running: closures over the values of the moment

def interpolate(table: list[tuple[float, float]], x: float) -> float:
    """A lookup: linear between its points, flat beyond its ends (as Vensim's are)."""
    if x <= table[0][0]:
        return table[0][1]
    if x >= table[-1][0]:
        return table[-1][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:], strict=False):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


class Compiled:
    """An equation ready to run: ``fn(values, params, state, change, init)`` (V, P, S, D, N). ``values`` maps a
    reference to its value now; ``state`` holds the hidden stocks of its delays (``slots`` of them),
    and ``change`` receives their rates of change; with ``init``, each delay starts in equilibrium
    with its input. ``decay`` holds, for each hidden stock, the share of it that leaves an hour (one
    over its stage time, T/order), for the integrator to choose its step and integrate it stably.

    Nothing that fails is hidden: a division by 0 (``/``, where ZIDZ or XIDZ was not written), the
    logarithm or square root of a number not above 0, a negative number to a fractional power and an
    overflow are each taken as 0, as Vensim's ZIDZ would, and counted in ``faults`` for the run's notes."""

    def __init__(self, tree, tables: dict[str, list] | None = None):
        self.tree = tree
        self.slots = 0
        self.decay: list[float] = []
        self.material: list[bool] = []      # each hidden stock: a material delay's contents (True), or a smoothed value
        self.faults: dict[str, int] = {}
        tables = tables or {}
        faults = self.faults

        def fault(what: str) -> float:
            faults[what] = faults.get(what, 0) + 1
            return 0.0

        def build(n):
            tag = n[0]
            if tag == "num":
                v = n[1]
                return lambda V, P, S, D, N: v
            if tag == "par":
                nm = n[1]
                return lambda V, P, S, D, N: P[nm]
            if tag == "ref":
                key = f"{n[1]}.{n[2]}"
                return lambda V, P, S, D, N: V[key]
            if tag == "neg":
                a = build(n[1])
                return lambda V, P, S, D, N: -a(V, P, S, D, N)
            if tag == "bin":
                a, b, op = build(n[2]), build(n[3]), n[1]
                if op == "+":
                    return lambda V, P, S, D, N: a(V, P, S, D, N) + b(V, P, S, D, N)
                if op == "-":
                    return lambda V, P, S, D, N: a(V, P, S, D, N) - b(V, P, S, D, N)
                if op == "*":
                    return lambda V, P, S, D, N: a(V, P, S, D, N) * b(V, P, S, D, N)
                if op == "/":
                    def div(V, P, S, D, N):
                        y = b(V, P, S, D, N)
                        return a(V, P, S, D, N) / y if y else fault("divided by 0")
                    return div

                def pw(V, P, S, D, N):
                    x, y = a(V, P, S, D, N), b(V, P, S, D, N)
                    try:
                        r = x ** y
                    except (OverflowError, ZeroDivisionError):
                        return fault("overflow, or 0 to a negative power")
                    if isinstance(r, complex):
                        return fault("a negative number to a fractional power")
                    return r
                return pw
            if tag == "lookup":
                a, table = build(n[2]), tables.get(n[1]) or [(0.0, 0.0)]
                return lambda V, P, S, D, N: interpolate(table, a(V, P, S, D, N))
            name, args = n[1], [build(x) for x in n[2]]
            if name == "MIN":
                return lambda V, P, S, D, N: min(f(V, P, S, D, N) for f in args)
            if name == "MAX":
                return lambda V, P, S, D, N: max(f(V, P, S, D, N) for f in args)
            if name in ("ZIDZ", "XIDZ"):
                a, b = args[0], args[1]
                x = args[2] if name == "XIDZ" else (lambda V, P, S, D, N: 0.0)

                def idz(V, P, S, D, N):
                    y = b(V, P, S, D, N)
                    return a(V, P, S, D, N) / y if y else x(V, P, S, D, N)
                return idz
            one = args[0]
            if name in ("ABS", "EXP", "LN", "SQRT"):
                def exp(x):
                    return math.exp(x) if x <= 700.0 else fault("overflow, or 0 to a negative power")
                g = {"ABS": abs, "EXP": exp,
                     "LN": lambda x: math.log(x) if x > 0 else fault("the logarithm of a number not above 0"),
                     "SQRT": lambda x: math.sqrt(x) if x >= 0 else fault("the square root of a negative number")}[name]
                return lambda V, P, S, D, N: g(one(V, P, S, D, N))
            k, order, T = self.slots, DELAYS[name], args[1]
            self.slots += order
            self.decay += [0.0] * order
            material = name.startswith("DELAY")
            self.material += [material] * order
            decay = self.decay

            def delay(V, P, S, D, N):
                x, t = one(V, P, S, D, N), max(T(V, P, S, D, N), 1e-12) / order
                if N:                                       # in equilibrium: as much leaves each stage as enters it
                    for j in range(order):
                        S[k + j] = x * t if material else x
                inflow = x
                for j in range(order):
                    decay[k + j] = 1.0 / t
                    if material:
                        out = S[k + j] / t
                        D[k + j] = inflow - out
                    else:
                        out = S[k + j]
                        D[k + j] = (inflow - out) / t
                    inflow = out
                return inflow
            return delay
        self.fn = build(tree)


# ---- units: products of powers of words, as written (ramps/h, alerts/ramp, KB/MP)

DIMENSIONLESS = {"", "1", "share", "fraction", "dimensionless", "ratio"}
IRREGULAR = {"hypotheses": "hypothesis", "analyses": "analysis", "people": "person", "statuses": "status"}
TIME = {"h": "h", "hr": "h", "hour": "h", "hours": "h"}
WILD = None          # a number written in an equation: it takes whatever unit it needs


def word(w: str) -> str:
    """A unit's word, singular: ramps and ramp are one unit."""
    if w in TIME:
        return TIME[w]
    if w in IRREGULAR:
        return IRREGULAR[w]
    if len(w) > 3 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 2 and w.endswith("s") and not w.endswith(("ss", "is", "us")):
        return w[:-1]
    return w


class UnitError(Exception):
    pass


def unit(text: str | None) -> dict | None:
    """A unit as {word: power}; None when it is not written. ``a/b/c`` is a over b and c."""
    if text is None:
        return None
    t = str(text).strip()
    if t.lower() in DIMENSIONLESS:
        return {}
    out: dict[str, Fraction] = {}
    for i, part in enumerate(re.split(r"\s*/\s*", t)):
        for f in re.split(r"\s*[*·]\s*|\s+", part):
            if not f or f == "1":
                continue
            m = re.match(r"^(.+?)(?:\^(-?\d+))?$", f)
            w, p = word(m.group(1)), Fraction(int(m.group(2) or 1))
            if w in DIMENSIONLESS:
                continue
            out[w] = out.get(w, Fraction(0)) + (p if i == 0 else -p)
    return {k: v for k, v in out.items() if v}


def unit_text(u: dict | None) -> str:
    if u is None:
        return "not known"
    if not u:
        return "1 (no unit)"

    def one(w, p):
        p = abs(p)
        return w if p == 1 else f"{w}^{p}"
    top = [one(w, p) for w, p in sorted(u.items()) if p > 0]
    bottom = [one(w, p) for w, p in sorted(u.items()) if p < 0]
    return ("·".join(top) or "1") + ("/" + "/".join(bottom) if bottom else "")


def _mul(a: dict, b: dict, sign: int = 1) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, Fraction(0)) + sign * v
    return {k: v for k, v in out.items() if v}


def units_of(tree, unit_of_ref, unit_of_par, tables_unit=None) -> tuple[dict | None, list[str]]:
    """The equation's unit, and every place its units disagree. ``unit_of_ref`` and ``unit_of_par``
    give a part's and a parameter's unit ({} for none, None for not written). A number takes the
    unit it needs; anything whose unit is not written makes what it is part of not known (and so
    not checked)."""
    problems: list[str] = []
    UNKNOWN = "?"

    def same(a, b, what) -> object:
        if a is WILD:
            return b
        if b is WILD or a == UNKNOWN or b == UNKNOWN:
            return a if b is WILD else UNKNOWN if UNKNOWN in (a, b) else a
        if a != b:
            problems.append(f"{what}: {unit_text(a)} and {unit_text(b)}")
            return UNKNOWN
        return a

    def go(n):
        tag = n[0]
        if tag == "num":
            return WILD
        if tag == "par":
            u = unit_of_par(n[1])
            return UNKNOWN if u is None else u
        if tag == "ref":
            u = unit_of_ref(f"{n[1]}.{n[2]}")
            return UNKNOWN if u is None else u
        if tag == "neg":
            return go(n[1])
        if tag == "bin":
            a, b, op = go(n[2]), go(n[3]), n[1]
            if op in "+-":
                return same(a, b, f"{text(n[2])} {op} {text(n[3])} adds unlike things")
            if op in "*/":
                if a == UNKNOWN or b == UNKNOWN:
                    return UNKNOWN
                a, b = a if a is not WILD else {}, b if b is not WILD else {}
                return _mul(a, b, 1 if op == "*" else -1)
            if a in (WILD, UNKNOWN):
                return a
            if n[3][0] == "num":
                p = Fraction(n[3][1]).limit_denominator(12)
                return {k: v * p for k, v in a.items()}
            if a:
                problems.append(f"{text(n)}: a quantity with a unit ({unit_text(a)}) raised to a power that is not a number")
            return a
        if tag == "lookup":
            go(n[2])
            u = (tables_unit or (lambda _: None))(n[1])
            return UNKNOWN if u is None else u
        name, args = n[1], [go(a) for a in n[2]]
        if name in ("MIN", "MAX"):
            u = args[0]
            for a in args[1:]:
                u = same(u, a, f"{name} of unlike things")
            return u
        if name == "ABS":
            return args[0]
        if name in ("ZIDZ", "XIDZ"):
            a, b = args[0], args[1]
            if a == UNKNOWN or b == UNKNOWN:
                q = UNKNOWN
            else:
                q = _mul(a if a is not WILD else {}, b if b is not WILD else {}, -1) if (a, b) != (WILD, WILD) else WILD
            return same(q, args[2], f"{name}'s value where its divisor is 0 is not in its unit") if name == "XIDZ" else q
        if name in ("EXP", "LN"):
            if args[0] not in (WILD, UNKNOWN) and args[0]:
                problems.append(f"{name} of {text(n[2][0])}, which has a unit ({unit_text(args[0])}): it takes a pure number")
            return {}
        if name == "SQRT":
            return args[0] if args[0] in (WILD, UNKNOWN) else {k: v / 2 for k, v in args[0].items()}
        t = args[1]
        if t not in (WILD, UNKNOWN) and t != {"h": Fraction(1)}:
            problems.append(f"{name}'s delay time {text(n[2][1])} is in {unit_text(t)}: a time, in hours")
        return args[0]
    u = go(tree)
    return (None if u in (UNKNOWN, WILD) else u), problems
