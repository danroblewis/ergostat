"""What the AI approver may be asked about (SPEC §12r): a positive allowlist of the changes a fix may make to one Python
program, read from its text before and after. ``escalate`` returns the reasons a person must decide; an empty list means
only that the AI may be asked. Every rule is "allowed only if", and anything it cannot parse, align or classify is a
reason (it fails closed). G0 preconditions; G1 alignment; S shaped values; G2 allowed statements; G3 taint; G4 control;
G5 exception paths. What it does not see (implicit raises, where standard output goes, other modules, time and memory,
and a builtin, ``print`` or ``json`` rebound by a call of the program's own unchanged code) is SPEC §12r's residuals."""

from __future__ import annotations

import ast
import builtins
import copy
import difflib

LINES = 40
CALLS = frozenset("len int float str bool abs min max round sorted list dict tuple set enumerate zip range isinstance "
                  "repr any all sum reversed".split())
TYPES = frozenset("int float str bool list dict tuple set".split())          # isinstance's type argument
METHODS = frozenset("get strip lower upper split startswith endswith replace join items keys values".split())
RAISES = frozenset("ValueError KeyError TypeError RuntimeError SystemExit".split())
PRINT_KW, DUMPS_KW = frozenset({"sep", "end", "flush"}), frozenset({"indent", "sort_keys", "ensure_ascii"})
TRUSTED = CALLS | RAISES | {"print", "json", "load", "loads", "dumps"}     # names whose meaning (a)-(c) rely on
DYNAMIC = frozenset("globals locals vars setattr delattr getattr exec eval compile __import__ __builtins__ "
                    "breakpoint".split())             # common ways to rebind a name out of sight: a list (residual 5)
FRAMES = frozenset({"modules", "f_globals", "f_locals", "f_builtins"})
MODULES = frozenset({"builtins", "importlib", "ctypes", "gc", "inspect"})
LISTS = ("body", "orelse", "handlers", "finalbody", "cases")
LOOPS, FUNCS = (ast.For, ast.AsyncFor, ast.While), (ast.FunctionDef, ast.AsyncFunctionDef)
GUARDED = (ast.Try, ast.TryStar, ast.With, ast.AsyncWith)
BUILTINS = frozenset(dir(builtins))                                     # names a read finds before any binding


def escalate(path: str, old: str, new: str, beside, tests=None, risk=None) -> list[str]:
    """The reasons a person must decide whether the fix ``old`` -> ``new`` of ``path`` is applied (``beside``: the names
    of the files next to it; ``tests`` and ``risk``: the fix's test result and impact risk). Empty: the AI may be asked."""
    why = []
    if not str(path).endswith(".py"):
        why.append(f"{path} is not a Python program")
    if tests != "passed":
        why.append(f"its test result is {tests or 'untested'}, not passed")
    if risk not in ("low", "medium"):
        why.append(f"its impact risk is {risk or 'not known'} (only low or medium)")
    sm = difflib.SequenceMatcher(None, old.splitlines(), new.splitlines(), autojunk=False)
    lines = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
    if lines > LINES:
        why.append(f"it changes {lines} lines (at most {LINES})")
    try:
        a, b = ast.parse(old), ast.parse(new)
    except Exception as e:                                   # (SyntaxError, ValueError on a NUL, RecursionError)
        return why + [f"a version does not parse ({type(e).__name__})"]
    try:
        return why + dynamic(b) + Fix(a, b, beside).reasons()
    except Exception as e:                                   # anything it cannot read: a person decides
        return why + [f"the guard could not read it ({type(e).__name__}: {e})"]


def dynamic(t) -> list[str]:
    """G0's module-wide refusals: ``import *``, ``builtins`` and the common spellings of rebinding a name out of the
    text's sight. A list, not a proof: a call the guard does not read can still rebind one (SPEC §12r residual 5)."""
    why = set()
    for n in ast.walk(t):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            mods = [n.module or ""] if isinstance(n, ast.ImportFrom) else [x.name for x in n.names]
            if any(x.name == "*" for x in n.names):
                why.add("the module holds an import *")
            if any(m.split(".")[0] in MODULES for m in mods) or (getattr(n, "module", None) == "sys" and
                                                                 any(x.name in FRAMES for x in n.names)):
                why.add(f"the module imports {', '.join(mods)}")
        elif isinstance(n, ast.Name) and n.id in DYNAMIC:
            why.add(f"the module refers to {n.id}")
        elif isinstance(n, ast.Attribute) and (n.attr.startswith("__") or n.attr in FRAMES):
            why.add(f"the module reads .{n.attr}")
        elif isinstance(n, ast.Attribute) and n.attr in TRUSTED and not isinstance(n.ctx, ast.Load):
            why.add(f"the module rebinds .{n.attr}")
    return sorted(why)


def header(n) -> str:
    """A statement's key: a simple one whole; a compound one without its bodies."""
    return ast.dump(strip(n))


def strip(n):
    """The part of a statement that runs when it is reached: a simple one whole, a compound one's header."""
    h = copy.copy(n)
    for f in LISTS:
        if hasattr(h, f):
            setattr(h, f, [])
    return h


def lists(n):
    return [getattr(n, f) for f in LISTS if isinstance(getattr(n, f, None), list)]


def inner(n) -> list:
    """Every statement (with handlers and cases) nested in ``n``, ``n`` left out."""
    out = []
    for lst in lists(n):
        for s in lst:
            out += [s, *inner(s)]
    return out


def align(a: list, b: list, changed: list, removed: list, owner) -> None:
    """G1: ``changed``: new statements that match nothing; ``removed``: (old statement, new owner, new list, index)."""
    sm = difflib.SequenceMatcher(None, [header(s) for s in a], [header(s) for s in b], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for x, y in zip(a[i1:i2], b[j1:j2], strict=True):
                for la, lb in zip(lists(x), lists(y), strict=True):     # (equal keys: the same kind of statement)
                    align(la, lb, changed, removed, y)
        else:
            changed += b[j1:j2]
            removed += [(x, owner, b, j1) for x in a[i1:i2]]


class Shapes:
    """S: which expressions of a module can only be JSON-type values, and which of its names are shaped."""

    def __init__(self, t, beside):
        self.binds: dict[str, list] = {}
        parent = {id(c): n for n in ast.walk(t) for c in ast.iter_child_nodes(n)}
        for n in ast.walk(t):
            if isinstance(n, ast.Name) and not isinstance(n.ctx, ast.Load):
                self.binds.setdefault(n.id, []).append(self.binding(n, parent))
            for name in names_bound_other(n):
                self.binds.setdefault(name, []).append(None)
        # An attribute stored or deleted could change what print writes to (sys.stdout.write = f) or what json.loads
        # runs (json._default_decoder = E()), so (b) and (c) need none, except a stdout pointed at a file by name.
        self.stores = [n for n in ast.walk(t) if isinstance(n, ast.Attribute) and not isinstance(n.ctx, ast.Load)
                       and not self.to_file(n, parent.get(id(n)))]
        js = self.binds.get("json")
        self.json = (js == [None] and any(isinstance(s, ast.Import) and any(x.name == "json" and x.asname is None
                                                                             for x in s.names) for s in t.body)
                     and sum(name == "json" for n in ast.walk(t) for name in names_bound_other(n)) == 1
                     and not any(str(f).split(".")[0] == "json" for f in beside) and not self.stores
                     and not any(isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "json"
                                 or isinstance(n, ast.Import) and any(x.name.startswith("json.") for x in n.names)
                                 for n in ast.walk(t))
                     and all(self.json_use(n, parent) for n in ast.walk(t) if isinstance(n, ast.Name)
                             and n.id == "json" and isinstance(n.ctx, ast.Load)))
        self.names: set[str] = set()
        while True:                                          # the least fixed point: from none shaped, widened
            more = {k for k, v in self.binds.items() if k not in self.names and self.widens(k, v)}
            if not more:
                break
            self.names |= more

    def widens(self, k, v) -> bool:
        """Every binding of ``k`` is shaped, a binding that reads ``k`` itself (``n += 1``) taken as shaped when ``k``
        names no builtin and no dunder: before its first binding, reading ``k`` raises, so each value it holds was made
        from shaped ones. One binding must be shaped without it (``n = n`` alone, or ``a = b; b = a``, has no start)."""
        own = k not in BUILTINS and not k.startswith("__")
        if own and not any(self.bound(x) for x in v):
            return False
        if own:
            self.names.add(k)
        try:
            return all(self.bound(x) for x in v)
        finally:
            if own:
                self.names.discard(k)

    def to_file(self, n, p) -> bool:
        """``X.stdout = open(<constants>)``, ``open`` bound nowhere: print then writes to a file, not to program code."""
        v = p.value if isinstance(p, ast.Assign) and p.targets == [n] else None
        return (n.attr == "stdout" and isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "open"
                and self.free("open") and all(isinstance(x, ast.Constant) for x in v.args)
                and all(k.arg and isinstance(k.value, ast.Constant) for k in v.keywords))

    @staticmethod
    def json_use(n, parent) -> bool:
        """``json`` read only as the receiver of a json.load, json.loads or json.dumps call (never aliased or passed)."""
        p = parent.get(id(n))
        c = parent.get(id(p))
        return isinstance(p, ast.Attribute) and p.attr in ("load", "loads", "dumps") and isinstance(c, ast.Call) \
            and c.func is p

    @staticmethod
    def binding(n, parent):
        """(how, expression) for a Name stored or deleted: ``value``, ``iter``, or None (never shaped)."""
        c, p = n, parent.get(id(n))
        while isinstance(p, (ast.Tuple, ast.List, ast.Starred)):
            c, p = p, parent.get(id(p))
        if isinstance(n.ctx, ast.Del):
            return None
        if isinstance(p, ast.Assign) and c in p.targets:
            return ("value", p.value)
        if isinstance(p, ast.AugAssign):
            return ("value", ast.BinOp(ast.Name(n.id, ast.Load()), p.op, p.value))
        if isinstance(p, ast.AnnAssign) and p.value is not None:
            return ("value", p.value)
        if isinstance(p, (ast.For, ast.comprehension)) and c is p.target and not getattr(p, "is_async", 0):
            return ("iter", p.iter)
        return None

    def bound(self, b) -> bool:
        if b is None:
            return False
        if b[0] == "value" and self.json_load(b[1]):
            return True
        return self.shaped(b[1])

    def json_load(self, e) -> bool:
        return (isinstance(e, ast.Call) and self.is_json(e.func, ("load", "loads")) and not e.keywords)

    def is_json(self, f, attrs) -> bool:
        return (self.json and isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "json"
                and f.attr in attrs)

    def free(self, name: str) -> bool:
        """A builtin's name is its own only when it is bound nowhere in the module."""
        return name not in self.binds

    def shaped(self, e) -> bool:
        s = self.shaped
        if e is None:
            return False
        if isinstance(e, ast.Constant):
            return type(e.value) in (str, int, float, bool, type(None))
        if isinstance(e, ast.JoinedStr):
            return all(isinstance(v, ast.Constant) or (isinstance(v, ast.FormattedValue) and s(v.value) and (
                v.format_spec is None or all(isinstance(x, ast.Constant) for x in v.format_spec.values)))
                for v in e.values)
        if isinstance(e, (ast.List, ast.Tuple, ast.Set)):
            return all(s(x) for x in e.elts)
        if isinstance(e, ast.Starred):
            return s(e.value)
        if isinstance(e, ast.Dict):
            return all(k is None or s(k) for k in e.keys) and all(s(v) for v in e.values)
        if isinstance(e, ast.Name):
            return isinstance(e.ctx, ast.Load) and e.id in self.names
        if isinstance(e, ast.Subscript):
            return s(e.value) and s(e.slice)
        if isinstance(e, ast.Slice):
            return all(x is None or s(x) for x in (e.lower, e.upper, e.step))
        if isinstance(e, ast.BinOp):
            return s(e.left) and s(e.right)
        if isinstance(e, ast.UnaryOp):
            return s(e.operand)
        if isinstance(e, ast.BoolOp):
            return all(s(x) for x in e.values)
        if isinstance(e, ast.Compare):
            return s(e.left) and all(s(x) for x in e.comparators)
        if isinstance(e, ast.IfExp):
            return s(e.test) and s(e.body) and s(e.orelse)
        if isinstance(e, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            parts = [e.key, e.value] if isinstance(e, ast.DictComp) else [e.elt]
            return all(not g.is_async and names_only(g.target) and s(g.iter) and all(s(x) for x in g.ifs)
                       for g in e.generators) and all(s(x) for x in parts)
        if isinstance(e, ast.Call):
            return self.call(e)
        return False                                         # attributes, lambda, await, yield, walrus, the rest

    def call(self, e) -> bool:
        f, args, kws = e.func, e.args, e.keywords
        if any(k.arg is None or not self.shaped(k.value) for k in kws):
            return False
        if isinstance(f, ast.Name) and self.free(f.id):
            if f.id == "isinstance" and not kws and len(args) == 2:                          # (a), its type argument
                t = args[1].elts if isinstance(args[1], ast.Tuple) else [args[1]]
                return self.shaped(args[0]) and all(isinstance(x, ast.Name) and x.id in TYPES and self.free(x.id)
                                                    for x in t)
            if f.id in CALLS - {"isinstance"}:                                                # (a)
                return not kws and all(self.shaped(x) for x in args)
            if f.id == "print":                                                               # (b)
                return not self.stores and all(k.arg in PRINT_KW for k in kws) and all(self.shaped(x) for x in args)
            return False
        if self.is_json(f, ("loads",)):                                                       # (c)
            return not kws and len(args) == 1 and self.shaped(args[0])
        if self.is_json(f, ("dumps",)):
            return all(k.arg in DUMPS_KW for k in kws) and len(args) == 1 and self.shaped(args[0])
        if isinstance(f, ast.Attribute) and f.attr in METHODS:                                # (d)
            return not kws and self.shaped(f.value) and all(self.shaped(x) for x in args)
        return False


def names_only(t) -> bool:
    return isinstance(t, ast.Name) or (isinstance(t, (ast.Tuple, ast.List)) and all(names_only(x) for x in t.elts))


def names_bound_other(n) -> list[str]:
    """The names a node binds other than by storing a Name: def, class, import, a parameter, a type parameter, except,
    a match capture."""
    if isinstance(n, (*FUNCS, ast.ClassDef)):
        return [n.name]
    if isinstance(n, (ast.Import, ast.ImportFrom)):
        return [x.asname or x.name.split(".")[0] for x in n.names]
    if isinstance(n, ast.arg):
        return [n.arg]
    if isinstance(n, (ast.TypeVar, ast.ParamSpec, ast.TypeVarTuple)):         # PEP 695: def f[print](x)
        return [n.name]
    if isinstance(n, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
        return [n.name] if n.name else []
    if isinstance(n, ast.MatchMapping):
        return [n.rest] if n.rest else []
    return []


def refs(e) -> set[str]:
    """The names ``e`` reads, and the attribute names it reads through (``Cfg.path``, ``j.p()``): G3 follows both."""
    return ({x.id for x in ast.walk(e) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}
            | {x.attr for x in ast.walk(e) if isinstance(x, ast.Attribute)})


def loads(n) -> set[str]:
    return refs(strip(n))


def holders(chain) -> set[str]:
    """The functions and classes enclosing a statement."""
    return {f.name for f in chain if isinstance(f, (*FUNCS, ast.ClassDef))}


def binds(n) -> set[str]:
    h = strip(n)
    return ({x.id for x in ast.walk(h) if isinstance(x, ast.Name) and not isinstance(x.ctx, ast.Load)}
            | {name for x in ast.walk(h) for name in names_bound_other(x)})


class Fix:
    """One fix read: the old and new modules aligned, then G2 to G5 on what changed and what it reaches."""

    def __init__(self, a, b, beside):
        self.old, self.new = a, b
        self.so, self.sn = Shapes(a, beside), Shapes(b, beside)
        self.changed_top: list = []
        self.removed: list = []
        align(a.body, b.body, self.changed_top, self.removed, None)
        self.at: dict[int, tuple] = {}                       # id(statement) -> (owner, list, index), the new module's
        self.index(b, None)

    def index(self, n, owner) -> None:
        for lst in lists(n):
            for i, s in enumerate(lst):
                self.at[id(s)] = (owner, lst, i)
                self.index(s, s)

    def chain(self, owner) -> list:
        out = []
        while owner is not None:
            out.append(owner)
            owner = self.at[id(owner)][0]
        return out

    def rest(self, owner, lst, i, stop) -> list:
        """The statements after position ``i`` of ``lst``, then after each enclosing one, up to ``stop`` (a function's
        body, or the module)."""
        out = []
        while True:
            for s in lst[i:]:
                out += [s, *inner(s)]
            if owner is None or isinstance(owner, stop):
                return out
            owner, lst, i = self.at[id(owner)]
            i += 1

    def reasons(self) -> list[str]:
        why: list[str] = []
        changed = {id(s): s for t in self.changed_top for s in (t, *inner(t))}
        removed = [(s, inside, owner, lst, i) for r, owner, lst, i in self.removed
                   for s, inside in ((r, []), *((x, self.within(r, x)) for x in inner(r)))]
        for s, *_ in removed:
            if (w := allowed(s, self.so)) is not None:
                why.append(f"removed, line {s.lineno}: {w}")
        funcs = {k for k, v in self.sn.binds.items() if v and all(x is None for x in v)
                 and all(isinstance(n, FUNCS) for n in ast.walk(self.new) if k in names_bound_other(n))}
        controlled: dict[int, object] = {}
        tainted: dict[int, object] = {}
        excused: set[int] = set()
        names: set[str] = set()
        hot: set[str] = set()                                # functions and classes holding a changed, removed,
        raised: set[str] = set()                             # controlled or tainted statement
        n0 = -1
        while n0 != (n0 := len(controlled) + len(tainted) + len(names) + len(hot) + len(raised)):
            for s, inside, owner, lst, i in removed:
                names |= binds(s)
                self.control(s, inside, owner, lst, i, controlled, raised, True)
                hot |= holders(self.chain(owner))
            for s in list(changed.values()) + list(controlled.values()):
                names |= binds(s)
                owner, lst, i = self.at[id(s)]
                self.control(s, [], owner, lst, i + 1, controlled, raised, id(s) in changed)
                hot |= holders(self.chain(owner))
            for k, (owner, lst, i) in list(self.at.items()):
                s = lst[i]
                if k in changed or k in controlled or not (loads(s) & (names | hot)):
                    continue
                if k not in tainted:
                    tainted[k] = s
                names |= binds(s)
                hot |= holders(self.chain(owner))
                if self.excuse(s, funcs, names | hot):
                    excused.add(k)
                if isinstance(s, (ast.If, ast.For, ast.While)):
                    for x in inner(s):
                        controlled.setdefault(id(x), x)
        why += sorted(raised) + self.uses(hot)
        for s in changed.values():
            if (w := allowed(s, self.sn)) is not None:
                why.append(f"changed, line {s.lineno}: {w}")
        for k, s in controlled.items():
            if k not in changed and (w := allowed(s, self.sn)) is not None:
                why.append(f"line {s.lineno}, steered by the change: {w}")
        for k, s in tainted.items():
            if k not in excused and k not in controlled and (w := allowed(s, self.sn)) is not None:
                why.append(f"line {s.lineno}, reading what the change made: {w}")
        why += self.exceptions([*changed.values(), *controlled.values(), *tainted.values()], removed)
        return list(dict.fromkeys(why))

    @staticmethod
    def within(r, x) -> list:
        """The statements of the removed ``r`` that enclose ``x`` (``r`` included)."""
        def path(n, acc):
            for s in (y for lst in lists(n) for y in lst):
                if s is x:
                    return acc + [n]
                if (got := path(s, acc + [n])) is not None:
                    return got
            return None
        return path(r, []) or [r]

    def control(self, s, inside, owner, lst, i, controlled, why, own) -> None:
        """G4: what a changed, removed or controlled continue, break, return or raise reaches. ``inside``: for a
        statement nested in a removed one, its removed enclosers; ``own``: changed or removed, not only controlled."""
        chain = [*inside[::-1], *self.chain(owner)]
        if isinstance(s, (ast.Continue, ast.Break)):
            loop = next((c for c in chain if isinstance(c, (*LOOPS, *FUNCS, ast.ClassDef))), None)
            if isinstance(loop, LOOPS) and not any(c is loop for c in inside):
                for x in [y for b in (loop.body, loop.orelse) for t in b for y in (t, *inner(t))]:
                    controlled.setdefault(id(x), x)
        elif isinstance(s, ast.Return):
            if inside and any(isinstance(c, FUNCS) for c in inside):
                return
            for x in self.rest(owner, lst, i, FUNCS):
                controlled.setdefault(id(x), x)
        elif isinstance(s, ast.Raise):
            if any(isinstance(c, FUNCS) for c in chain):
                if own and not any(isinstance(c, FUNCS) for c in inside):
                    why.add(f"line {s.lineno}: a raise changed or removed inside a function")
                return
            for x in self.rest(owner, lst, i, ()):
                controlled.setdefault(id(x), x)

    def uses(self, hot) -> list[str]:
        """A function or class holding the change is reached only by a call G3 follows: never decorated (a decorator
        may register it), never read other than as a callee (passed on, stored, or a class's attribute or base). A
        class holding it has no base, keyword or type parameter: a metaclass or a base's ``__init_subclass__`` would be
        given its namespace when it is defined, with no call to follow."""
        why = [f"line {n.lineno}: {n.name} holds the change and is decorated" for n in ast.walk(self.new)
               if isinstance(n, (*FUNCS, ast.ClassDef)) and n.name in hot and n.decorator_list]
        why += [f"line {n.lineno}: {n.name} holds the change and has a base or keyword" for n in ast.walk(self.new)
                if isinstance(n, ast.ClassDef) and n.name in hot and (n.bases or n.keywords or n.type_params)]
        callees = {id(c.func) for c in ast.walk(self.new) if isinstance(c, ast.Call)}
        for n in ast.walk(self.new):
            ref = (n.id if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) else
                   n.attr if isinstance(n, ast.Attribute) else None)
            if ref in hot and id(n) not in callees:
                why.append(f"line {n.lineno}: {ref} holds the change and is used other than by a call")
        return why

    @staticmethod
    def excuse(s, funcs, hot) -> bool:
        """G3's exception: only ``NAME = f(args)`` or ``f(args)``, ``f`` a module function, no argument tainted."""
        v = s.value if isinstance(s, ast.Expr) else s.value if (isinstance(s, ast.Assign) and len(s.targets) == 1
                                                                 and isinstance(s.targets[0], ast.Name)) else None
        if not (isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in funcs):
            return False
        return not any(refs(a) & hot for a in (*v.args, *v.keywords))

    def exceptions(self, stmts, removed) -> list[str]:
        """G5: nothing reached by the change lexically inside a try or with; inside a function, no try or with at all."""
        why, infunc = [], False
        for s in stmts:
            chain = self.chain(self.at[id(s)][0])
            if any(isinstance(c, GUARDED) for c in chain):
                why.append(f"line {s.lineno}: inside a try or with")
            infunc |= any(isinstance(c, FUNCS) for c in chain)
        for s, inside, owner, *_ in removed:
            chain = [*inside, *self.chain(owner)]
            if any(isinstance(c, GUARDED) for c in chain):
                why.append(f"removed, line {s.lineno}: inside a try or with")
            infunc |= any(isinstance(c, FUNCS) for c in chain)
        if infunc and any(isinstance(n, GUARDED) for n in ast.walk(self.new)):
            why.append("the change is inside a function, and the module holds a try or with")
        return why


def allowed(s, sh: Shapes) -> str | None:
    """G2: None when the statement is one a fix may make; else why not."""
    if isinstance(s, (ast.Assign, ast.AugAssign)):
        ts = s.targets if isinstance(s, ast.Assign) else [s.target]
        if not all(names_only(t) or (isinstance(t, ast.Starred) and isinstance(t.value, ast.Name)) for t in ts):
            return "an assignment to something other than names"
        if isinstance(s, ast.AugAssign) and not sh.shaped(ast.Name(s.target.id, ast.Load())):
            return f"an augmented assignment to {s.target.id}, a name not shaped"
        return None if sh.shaped(s.value) else "an assignment of a value not shaped"
    if isinstance(s, ast.Expr):
        c = s.value
        ok = isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "print" and sh.shaped(c)
        return None if ok else "an expression other than a print of shaped values"
    if isinstance(s, ast.If):
        return None if sh.shaped(s.test) else "an if whose test is not shaped"
    if isinstance(s, ast.For):
        return None if names_only(s.target) and sh.shaped(s.iter) else "a for not over a shaped value into names"
    if isinstance(s, (ast.Pass, ast.Continue, ast.Break)):
        return None
    if isinstance(s, ast.Return):
        return None if s.value is None or sh.shaped(s.value) else "a return of a value not shaped"
    if isinstance(s, ast.Assert):
        return None if sh.shaped(s.test) and (s.msg is None or sh.shaped(s.msg)) else "an assert not shaped"
    if isinstance(s, ast.Raise):
        e = s.exc
        ok = (s.cause is None and isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id in RAISES
              and sh.free(e.func.id) and not e.keywords and all(sh.shaped(x) for x in e.args))
        return None if ok else "a raise other than of a listed exception with shaped arguments"
    return f"a {type(s).__name__.lower()} statement"
