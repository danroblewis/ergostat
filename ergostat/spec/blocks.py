"""The built-in blocks (SPEC §9.2): small functions ergostat computes itself on every reading of
their inputs. Each keeps the little state it needs (a hysteresis latch, a delay line, a count).

A block is stepped with ``get``, which returns a signal's current value (None: not known yet),
and the time. It returns its output, or None while it cannot say."""

from __future__ import annotations

import ast
import math
import operator
import time as _time
from collections import deque

from .ir import Block, Ref, Setpoint, Spec


class ExprError(Exception):
    pass


class TableError(Exception):
    pass


# ---- expressions: arithmetic only, no names but the block's own inputs

FUNCS = {"min": min, "max": max, "abs": abs, "round": round, "sqrt": math.sqrt, "floor": math.floor, "ceil": math.ceil,
         "log": math.log, "exp": math.exp}
BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Eq: operator.eq,
       ast.NotEq: operator.ne}


def compile_expr(text: str) -> ast.Expression:
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"not an expression ({e.msg})") from None
    for node in ast.walk(tree):
        ok = isinstance(node, ast.Expression | ast.BinOp | ast.UnaryOp | ast.Compare | ast.BoolOp | ast.IfExp | ast.Call |
                        ast.Name | ast.Constant | ast.Load | ast.operator | ast.unaryop | ast.cmpop | ast.boolop)
        if not ok:
            raise ExprError(f"{type(node).__name__} is not allowed: arithmetic, comparisons, and/or, x if c else y, "
                            f"and {', '.join(FUNCS)}")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in FUNCS):
            raise ExprError(f"only these functions: {', '.join(FUNCS)}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, int | float):
            raise ExprError("only numbers")
        unary = isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd | ast.Not)
        if isinstance(node, ast.BinOp | ast.UnaryOp) and type(node.op) not in BIN and not unary:
            raise ExprError(f"operator {type(node.op).__name__} is not allowed")
    return tree


def expr_names(tree: ast.Expression) -> set[str]:
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - calls


def eval_expr(tree, env: dict) -> float:
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in env:
                raise ExprError(f"{n.id} is not one of its inputs")
            return env[n.id]
        if isinstance(n, ast.BinOp):
            return BIN[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else (not v) if isinstance(n.op, ast.Not) else v
        if isinstance(n, ast.Compare):
            left = ev(n.left)
            for op, right in zip(n.ops, n.comparators, strict=True):
                r = ev(right)
                if not CMP[type(op)](left, r):
                    return 0
                left = r
            return 1
        if isinstance(n, ast.BoolOp):
            vals = [ev(v) for v in n.values]
            return (all(vals) if isinstance(n.op, ast.And) else any(vals)) and 1 or 0
        if isinstance(n, ast.IfExp):
            return ev(n.body) if ev(n.test) else ev(n.orelse)
        if isinstance(n, ast.Call):
            return FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ExprError(type(n).__name__)
    return float(ev(tree))


# ---- tables

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def read_table(kind: str, raw):
    """A lookup's points (x → y, sorted), or a schedule's (minute of the week → value)."""
    if kind == "lookup":
        pts = list(raw.items()) if isinstance(raw, dict) else raw if isinstance(raw, list) else None
        if not pts:
            raise TableError("points, as a map (0: 0, 100: 5) or a list of [x, y]")
        out = []
        for p in pts:
            try:
                x, y = p
                out.append((float(x), float(y)))
            except (TypeError, ValueError):
                raise TableError(f"{p!r} is not a point: x and y, both numbers") from None
        return sorted(out)
    if not isinstance(raw, dict) or not raw:
        raise TableError('times to values: "09:00": 5, "18:00": 1 (daily), or "mon 09:00": 5 (weekly)')
    out = []
    for k, v in raw.items():
        words = str(k).split()
        days = list(range(7))
        if len(words) == 2:
            d = words[0].lower()[:3]
            if "-" in words[0]:
                a, b = (x.lower()[:3] for x in words[0].split("-", 1))
                if a not in DAYS or b not in DAYS:
                    raise TableError(f"{k}: days are mon..sun")
                days = list(range(DAYS.index(a), DAYS.index(b) + 1))
            elif d in DAYS:
                days = [DAYS.index(d)]
            else:
                raise TableError(f"{k}: days are mon..sun")
            words = words[1:]
        try:
            h, m = (int(x) for x in words[0].split(":"))
            assert 0 <= h < 24 and 0 <= m < 60
            val = float(v)
        except (ValueError, AssertionError, IndexError, TypeError):
            raise TableError(f"{k}: {v!r}: a time HH:MM and a number") from None
        for d in days:
            out.append((d * 1440 + h * 60 + m, val))
    return sorted(out)


def schedule_value(table, now: float) -> float:
    lt = _time.localtime(now)
    minute = lt.tm_wday * 1440 + lt.tm_hour * 60 + lt.tm_min
    before = [v for t, v in table if t <= minute]
    return before[-1] if before else table[-1][1]          # before the first entry: last week's last


def lookup_value(table, x: float) -> float:
    if x <= table[0][0]:
        return table[0][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:], strict=False):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 != x0 else y1
    return table[-1][1]


# ---- the blocks

class Builtin:
    def __init__(self, block: Block, spec: Spec):
        self.b, self.spec = block, spec
        self.out: float | None = None
        self.changed_at: float | None = None
        self.p = block.params

    def first(self, get) -> float | None:
        refs = list(self.b.inputs.values())
        return get(refs[0]) if refs else None

    def step(self, get, now: float) -> float | None:
        v = self.compute(get, now)
        if v is not None and (self.out is None or v != self.out):
            self.changed_at = now
        if v is not None:
            self.out = v
        return self.out if v is None and self.keeps() else v

    def keeps(self) -> bool:
        """Whether its last output stands while an input is unknown (a latch does; arithmetic does not)."""
        return False

    def compute(self, get, now: float) -> float | None:
        raise NotImplementedError


class OnOff(Builtin):
    """On while its goal is off; off again once the goal's value is back to ``until`` (or the goal
    holds). ``min-on`` and ``min-off`` keep it from chattering."""

    def keeps(self):
        return True

    def compute(self, get, now):
        g = self.spec.goals[self.b.goal]
        off = get(Ref("goal", g.name, "off"))
        y = get(g.of)                                      # (None while it is stale and seen as off: SPEC §9.6)
        if off is None or (y is None and not off):
            return None
        on = bool(self.out)
        held = now - self.changed_at if self.changed_at is not None else math.inf
        if not on:
            return 1.0 if off and held >= (self.p.get("min-off") or 0) else 0.0
        until: Setpoint | None = self.p.get("until")
        done = (not until.outside(y)) if until and y is not None else not off
        return 0.0 if done and held >= (self.p.get("min-on") or 0) else 1.0


class Compare(Builtin):
    def keeps(self):
        return True

    def compute(self, get, now):
        x = self.first(get)
        if x is None:
            return None
        on = bool(self.out)
        if self.p.get("above") is not None:
            a = float(self.p["above"])
            back = float(self.p.get("back-below", a))
            return 1.0 if (x > a or (on and x > back)) else 0.0
        b = float(self.p["below"])
        back = float(self.p.get("back-above", b))
        return 1.0 if (x < b or (on and x < back)) else 0.0


class Proportional(Builtin):
    """gain × |error|: the size of the correction (its direction is the valve's: the flow it moves),
    clamped to ``min`` and ``max``."""

    def compute(self, get, now):
        e = get(Ref("goal", self.b.goal, "error"))
        if e is None:
            return None
        u = float(self.p["gain"]) * abs(e)
        if self.p.get("max") is not None:
            u = min(u, float(self.p["max"]))
        if self.p.get("min") is not None and u > 0:
            u = max(u, float(self.p["min"]))
        return u


class Limit(Builtin):
    def compute(self, get, now):
        x = self.first(get)
        if x is None:
            return None
        if self.p.get("max") is not None:
            x = min(x, float(self.p["max"]))
        if self.p.get("min") is not None:
            x = max(x, float(self.p["min"]))
        rate = self.p.get("rate")
        last_t, self.last_t = getattr(self, "last_t", None), now
        if rate is not None and self.out is not None and last_t is not None:
            most = float(rate) * (now - last_t) / 3600
            x = max(self.out - most, min(self.out + most, x))
        return x


class Delay(Builtin):
    def __init__(self, block, spec):
        super().__init__(block, spec)
        self.line: deque = deque()

    def compute(self, get, now):
        x = self.first(get)
        if x is not None:
            self.line.append((now, x))
        d = float(self.p["delay"])
        out = None
        while self.line and self.line[0][0] <= now - d:
            out = self.line.popleft()[1]
            self.held = out
        return out if out is not None else getattr(self, "held", None)


class Schedule(Builtin):
    def compute(self, get, now):
        return schedule_value(self.p["table"], now)


class Lookup(Builtin):
    def compute(self, get, now):
        x = self.first(get)
        return None if x is None else lookup_value(self.p["table"], x)


class Select(Builtin):
    def compute(self, get, now):
        xs = [get(r) for r in self.b.inputs.values()]
        xs = [x for x in xs if x is not None]
        if not xs:
            return None
        pick = self.p["pick"]
        if pick == "min":
            return min(xs)
        if pick == "max":
            return max(xs)
        return next((x for x in xs if x), 0.0)


class Expr(Builtin):
    def __init__(self, block, spec):
        super().__init__(block, spec)
        self.tree = compile_expr(str(self.p["expr"]))

    def compute(self, get, now):
        env = {}
        for port, r in self.b.inputs.items():
            v = get(r)
            if v is None:
                return None
            env[port.replace("-", "_")] = v
        try:
            return eval_expr(self.tree, env)
        except (ExprError, ArithmeticError, ValueError, TypeError):
            return None


class Timer(Builtin):
    def compute(self, get, now):
        x = self.first(get)
        if x is None:
            return None
        if not x:
            self.since = None
            return 0.0
        if getattr(self, "since", None) is None:
            self.since = now
        return 1.0 if now - self.since >= float(self.p["after"]) else 0.0


class Counter(Builtin):
    def compute(self, get, now):
        x = self.first(get)
        if not hasattr(self, "n"):
            self.n, self.was, self.reset_at = 0.0, False, now
        if self.p.get("reset") and now - self.reset_at >= float(self.p["reset"]):
            self.n, self.reset_at = 0.0, now
        if x is not None:
            if x and not self.was:
                self.n += 1
            self.was = bool(x)
        return self.n


class Alarm(Builtin):
    def keeps(self):
        return True

    def compute(self, get, now):
        x = self.first(get)
        if x is None:
            return None
        out = (self.p.get("above") is not None and x > float(self.p["above"])) or \
              (self.p.get("below") is not None and x < float(self.p["below"]))
        if not out:
            self.since = None
            return 0.0
        if getattr(self, "since", None) is None:
            self.since = now
        return 1.0 if now - self.since >= float(self.p.get("for") or 0) else 0.0


TYPES = {"onoff": OnOff, "compare": Compare, "proportional": Proportional, "limit": Limit, "delay": Delay,
         "schedule": Schedule, "lookup": Lookup, "select": Select, "expr": Expr, "timer": Timer, "counter": Counter,
         "alarm": Alarm}


def make(block: Block, spec: Spec) -> Builtin:
    return TYPES[block.type](block, spec)


def order(spec: Spec) -> list[str]:
    """The built-ins in an order where each comes after the built-ins it reads (a delay breaks a
    cycle: it reads its input's last value)."""
    names = [n for n, b in spec.blocks.items() if b.builtin and b.type != "judge"]   # the judge runs on its own clock
    deps: dict[str, set[str]] = {n: set() for n in names}
    for n in names:
        b = spec.blocks[n]
        for r in b.inputs.values():
            if r.kind == "block" and r.name in deps and spec.blocks[n].type != "delay":
                deps[n].add(r.name)
        for t in b.targets():
            if t.kind == "block" and t.name in deps and spec.blocks[t.name].type != "delay":
                deps[t.name].add(n)
        if b.goal:   # a goal set by a built-in (a cascade) is computed before the blocks reading it
            for m in names:
                if any(t.kind == "goal" and t.name == b.goal for t in spec.blocks[m].targets()) and m != n:
                    deps[n].add(m)
    out: list[str] = []
    seen: set[str] = set()

    def visit(n, stack=()):
        if n in seen or n in stack:
            return
        for d in sorted(deps[n]):
            visit(d, (*stack, n))
        seen.add(n)
        out.append(n)
    for n in sorted(names):
        visit(n)
    return out
