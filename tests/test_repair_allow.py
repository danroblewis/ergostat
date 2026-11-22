"""The AI approver's guard (SPEC §12r, ``ergostat.repair.allow``): a positive allowlist of what a fix may change, read
from the program's text before and after. Every refusal has an accepted twin, so a guard that refuses everything, or
accepts everything, fails here."""

import pytest

from ergostat.repair.allow import escalate
from tests.test_repair2 import BROKEN, FIXED


def esc(old, new, beside=("answer.json", "notes.txt"), tests="passed", risk="low", path="collect.py"):
    return escalate(path, old, new, list(beside), tests=tests, risk=risk)


def change(extra_old, extra_new, base=BROKEN, **kw):
    """``base`` with ``extra_old`` added, changed into ``base`` with ``extra_new`` added."""
    return esc(base + extra_old, base + extra_new, **kw)


def refused(why, *words):
    assert why, "refused"
    assert all(any(w in r for r in why) for w in words), why
    return True


# ---- accepted


def test_accepts_the_shape_fix():
    assert esc(BROKEN, FIXED) == []


def test_accepts_get_default_if_continue_and_int():
    new = BROKEN.replace('for issue in answer["issues"]:\n', 'for issue in answer.get("values", []):\n'
                         '    n = int(issue.get("n", 0))\n    if issue.get("id") is None:\n        continue\n')
    assert esc(BROKEN, new.replace("issue['key']", "issue['id']")) == []


# ---- G0


def test_refuses_untested_failed_high_risk_non_python_and_large():
    assert esc(BROKEN, FIXED) == []
    assert refused(esc(BROKEN, FIXED, tests=None), "untested")
    assert refused(esc(BROKEN, FIXED, tests="failed"), "failed")
    assert refused(esc(BROKEN, FIXED, risk="high"), "high")
    assert refused(esc(BROKEN, FIXED, risk=None), "not known")
    assert refused(esc(BROKEN, FIXED, path="collect.sh"), "not a Python program")
    assert esc(BROKEN, FIXED + "x = 1\n" * 38) == []                    # 40 lines changed: within
    assert refused(esc(BROKEN, FIXED + "x = 1\n" * 39), "41 lines")


def test_refuses_unparseable():
    assert esc(BROKEN, FIXED) == []
    assert refused(esc(BROKEN, FIXED + "def (:\n"), "does not parse")
    assert refused(esc(BROKEN + "def (:\n", FIXED), "does not parse")


# ---- the bypasses listed in GAPS


def test_refuses_vars_os_system():
    assert change("", "print('x')\n") == []
    assert refused(change("", "vars(os)['sys'+'tem']('x')\n"), "vars")


def test_refuses_sys_modules():
    base = "import sys\n" + BROKEN
    assert change("", "print('x')\n", base=base) == []
    assert refused(change("", "m = sys.modules['os']\n", base=base), ".modules")


def test_refuses_dunder_subclasses():
    assert change("", "x = ()\n") == []
    assert refused(change("", "x = ().__class__.__subclasses__()\n"), ".__class__")


def test_refuses_existing_subprocess_given_new_args():
    base = "import subprocess\n" + BROKEN
    assert change("subprocess.run(['echo', 'x'])\nprint('a')\n", "subprocess.run(['echo', 'x'])\nprint('b')\n",
                  base=base) == []
    assert refused(change("subprocess.run(['echo', 'x'])\n", "subprocess.run(['sh', '-c', answer['x']])\n",
                          base=base), "changed, line", "expression other than")


@pytest.mark.parametrize("head,call", [("", "os.chmod('a', 511)"), ("from pathlib import Path\n", "Path('a').rename('b')"),
                                       ("import marshal\n", "marshal.loads(b'')")])
def test_refuses_unlisted_calls(head, call):
    assert change("", "print('a')\n", base=head + BROKEN) == []
    assert refused(change("", call + "\n", base=head + BROKEN), "changed, line", "expression other than")


def test_refuses_path_literal_into_existing_open():
    old = BROKEN.replace('answer = json.loads(open("answer.json").read())',
                         'fn = "answer.json"\nanswer = json.loads(open(fn).read())')
    assert refused(esc(old, old.replace('fn = "answer.json"', 'fn = "../x"')), "reading what the change made")
    assert change('fn = "a"\nprint(fn)\n', 'fn = "../x"\nprint(fn)\n') == []


def test_refuses_new_import():
    assert esc(BROKEN, FIXED) == []
    assert refused(esc(BROKEN, FIXED + "import shutil\n"), "import")


def test_refuses_attribute_and_subscript_stores():
    base = BROKEN + "d = {}\n"
    assert change("", "e = {'k': 1}\n", base=base) == []
    assert refused(change("", "d['k'] = 1\n", base=base), "other than names")
    assert refused(change("", "d.a = 1\n", base=base), "other than names")


def test_refuses_print_file_kw():
    assert change("", "print(1, end='', sep=' ', flush=True)\n") == []
    assert refused(change("", "print(1, file=None)\n"), "print")


# ---- shadowing


@pytest.mark.parametrize("shadow,twin", [
    ("def print(*a):\n    pass\n", "def show(*a):\n    pass\n"),
    ("from rich import print\n", "from rich import box\n"),
    ("len = os.system\n", "size = os.system\n"),
    ("for len in []:\n    pass\n", "for k in []:\n    pass\n"),
    ("try:\n    pass\nexcept ValueError as len:\n    pass\n", "try:\n    pass\nexcept ValueError as e:\n    pass\n"),
    ("with open('x') as len:\n    pass\n", "with open('x') as f:\n    pass\n"),
    ("class C:\n    print = 1\n", "class C:\n    show = 1\n"),
    ("def f(len):\n    pass\n", "def f(n):\n    pass\n"),
])
def test_refuses_shadowed_builtin_or_print(shadow, twin):
    assert change(twin, twin + "print(len(answer))\n") == []
    assert refused(change(shadow, shadow + "print(len(answer))\n"), "changed, line", "print of shaped")


@pytest.mark.parametrize("bad,twin,why", [("from os import *\n", "from os import path\n", "import *"),
                                          ("import builtins\n", "import string\n", "imports builtins"),
                                          ("x = __builtins__\n", "x = __name__\n", "refers to __builtins__")])
def test_refuses_import_star_and_builtins(bad, twin, why):
    assert change(twin, twin + "print('a')\n") == []
    assert refused(change(bad, bad + "print('a')\n"), why)


@pytest.mark.parametrize("bad,twin,beside", [("json = yaml\n", "data = yaml\n", None),
                                             ("import yaml as json\n", "import yaml as y\n", None),
                                             ("", "", ["json.py", "answer.json"])])
def test_refuses_json_rebound_or_beside(bad, twin, beside):
    add = "v = json.loads('1')\nprint(v)\n"
    assert change(twin, twin + add) == []
    assert refused(change(bad, bad + add, **({"beside": beside} if beside else {})), "changed, line", "value not shaped")


SINK = "class E:\n    def decode(self, s):\n        os.system(s)\n    encode = decode\n"
FIX = ("cmd = 'ls'\nx = 1\n", "cmd = 'touch /tmp/PWNED'\nx = json.{f}(cmd)\n")


@pytest.mark.parametrize("bad,f", [("json._default_decoder = E()\n", "loads"), ("json._default_encoder = E()\n", "dumps"),
                                   ("json.decoder.JSONDecoder.decode = E.decode\n", "loads"),
                                   ("from json import decoder\ndecoder.JSONDecoder.decode = E.decode\n", "loads"),
                                   ("from json import decoder\n", "loads"), ("import json.decoder as jd\n", "loads"),
                                   ("j = json\n", "loads"), ("o = E()\no.x = 1\n", "loads")])
def test_refuses_json_internals_changed(bad, f):
    """json.loads runs the module's ``_default_decoder``: json is trusted only when it is read as nothing but the
    receiver of load, loads or dumps, no other import names it, and no attribute is stored (review round 3)."""
    old, new = FIX[0], FIX[1].format(f=f)
    assert change(SINK + old, SINK + new) == []
    assert refused(change(SINK + bad + old, SINK + bad + new), "changed, line", "value not shaped")


@pytest.mark.parametrize("bad", ["class W:\n    def write(self, s):\n        os.system(s)\nimport sys\nsys.stdout = W()\n",
                                 "import sys\nsys.stdout.write = os.system\n",
                                 "import sys\nout = sys.stdout\nout.write = os.system\n",
                                 "import sys\nsys.stdout = open(input())\n"])
def test_refuses_print_into_program_code(bad):
    """print writes to sys.stdout's write(): a stdout of the program's own, or one whose write is replaced, would run
    program code on what a changed print is given. Only ``X.stdout = open(<constants>)`` is let through (residual 2)."""
    assert change("print('a')\n", "print('rm -rf ~')\n") == []
    assert change("import sys\nsys.stdout = open('out', 'w')\nprint('a')\n",
                  "import sys\nsys.stdout = open('out', 'w')\nprint('rm -rf ~')\n") == []
    assert refused(change(bad + "print('a')\n", bad + "print('rm -rf ~')\n"), "changed, line")


@pytest.mark.parametrize("bad", ["globals()['len'] = os.system\n", "import sys\nsetattr(sys.modules[__name__], 'len', 1)\n",
                                 "exec('len = 1')\n", "import sys\nsys.modules['json'] = sys\n",
                                 "import importlib\nm = importlib.import_module('builtins')\n", "os.len = 1\n"])
def test_refuses_dynamic_rebinding(bad):
    add = "print(len(answer))\n"
    assert change("config = {'len': 1}\n", "config = {'len': 1}\n" + add) == []
    assert refused(change(bad, bad + add), "the module")


# ---- shaped values


def test_refuses_unshaped_name():
    assert refused(change("env = os.environ\n", "env = os.environ\nprint(env['TOKEN'])\n"), "print")
    assert change("env = json.loads(s)\n", "env = json.loads(s)\nprint(env['TOKEN'])\n") == []


def test_unbound_name_not_shaped():
    assert change("", "print(len(answer), isinstance(answer, (dict, list)))\n") == []
    for e in ("open", "__loader__", "exit", "int"):              # a builtin, as a value, is not shaped either
        assert refused(change("", f"print({e})\n"), "print"), e


def test_shaped_names_from_nothing_are_not_shaped():
    assert refused(change("a = b\nb = a\n", "a = b\nb = a\nprint(a)\n"), "print"), "a cycle is not shaped on nothing"
    assert change("a = 1\nb = a\n", "a = 1\nb = a\nprint(b)\n") == []


HEAD = "from pathlib import Path\n" + BROKEN
CH = ("x = 1\n", "x = d[0].replace('a', '../x')\n")
FILL = "def fill(y):\n    y.append(Path('v'))\n"
EVIL = "class Evil:\n    def __eq__(self, o):\n        o.append(Path('v'))\n    def join(self, o):\n        o.append(Path('v'))\n"


@pytest.mark.parametrize("bad, twin", [
    ("d = []\nfor f in os.listdir('.'):\n    d.append(Path(f))\n",          # append
     "d = []\nfor f in os.listdir('.'):\n    print(f)\n"),
    ("d = json.loads(s)\nd[0] = os.environ\n", "d = json.loads(s)\ne = d[0]\n"),            # a subscript store
    ("d = json.loads(s)\nd.update(os.environ)\n", "d = json.loads(s)\nprint(d.keys())\n"),  # a method outside (d)
    (FILL + "d = []\nfill(d)\n", FILL + "d = []\nfill([])\n"),                             # a call that receives it
    ("d = []\ne = d\ne.append(Path('v'))\n", "d = []\ne = d\nprint(e)\n"),                  # an alias
    ("d = [[]]\ne = d[0]\ne.append(Path('v'))\n", "d = [[]]\ne = d[0]\nprint(len(e))\n"),   # an element alias
    ("d = [[]]\nfor e in d:\n    e.append(Path('v'))\n", "d = [[]]\nfor e in d:\n    print(e)\n"),  # a loop's
    ("d = [[]]\nes = [e for e in d]\nes[0].append(1)\n", "d = [[]]\nes = [e for e in d]\nprint(es)\n"),
    (EVIL + "d = []\nif Evil() == d:\n    pass\n", EVIL + "d = []\nif [] == d:\n    pass\n"),  # obj.__eq__(d)
    (EVIL + "d = []\nEvil().join(d)\n", EVIL + "d = []\n'-'.join(d)\n"),                   # obj.join(d)
    ("d = []\ndef mk():\n    return d\nmk().append(Path('v'))\n",                          # returned, then filled
     "d = []\ndef mk():\n    return d\nprint(mk())\n"),
    ("class C:\n    d = []\nC.d.append(Path('v'))\nd = []\n",                              # a class's namespace
     "class C:\n    k = []\nC.k.append(Path('v'))\nd = []\n"),
    ("d = []\ncb = lambda: d\ncb().append(Path('v'))\n", "d = []\ncb = lambda: []\ncb().append(Path('v'))\n"),
])
def test_refuses_container_filled_by_unchanged_code(bad, twin):
    """A shaped name's object can be changed through any name holding it, so names that may hold one object are read
    as one: a store into it, a method outside (d), a call outside (a) to (d), or an operation with an unshaped part
    makes none of them shaped (review round 5). Filling one in place, even with shaped values, goes to the person."""
    assert change(*CH, base=HEAD + twin) == []
    assert refused(change(*CH, base=HEAD + bad), "changed, line", "value not shaped")


def test_refuses_the_reviews_container_traces():
    paths = "paths = []\nfor f in os.listdir('.'):\n    paths.append(Path(f))\nfor p in paths:\n"
    assert refused(change(paths + "    print(p)\n", paths + "    print(p.replace('../../victim'))\n", base=HEAD),
                   "print of shaped")
    plain = "paths = ['a']\nfor p in paths:\n"
    assert change(plain + "    print(p)\n", plain + "    print(p.replace('../../victim'))\n", base=HEAD) == []
    for fill, ok in (("d['env'] = os.environ\n", False), ("", True)):
        prog = "d = json.loads(s)\n" + fill
        why = change(prog + "print(d.get('a'))\n", prog + "print(d.get('env'))\n")
        assert (why == []) is ok, (fill, why)


USED_UP = "protect = ('a', 'b')\ngen = {gen}\nprint({show})\nkeep = list(gen)\nif len(keep) == 0:\n    os.system('x')\n"


@pytest.mark.parametrize("bad, twin", [
    ("(x for x in protect)", "tuple(x for x in protect)"),          # review 7's trace: a generator held by a name
    ("enumerate(protect)", "list(enumerate(protect))"),
    ("zip(protect, protect)", "tuple(zip(protect, protect))"),
    ("reversed(protect)", "sorted(protect)"),
    ("[zip(protect)][0]", "[list(zip(protect))][0]"),                # an iterator kept in a display
    ("max([enumerate(protect)])", "max(enumerate(protect))"),        # an iterator handed back by a call
])
def test_refuses_iterator_used_up_by_a_changed_read(bad, twin):
    """A generator or iterator holds state that reading it uses up, so one kept by a name lets a changed read empty
    what unchanged code reads next (review 7). It is shaped only where it is used up in the same expression."""
    fix = ("1", "list(gen)")
    assert change(USED_UP.format(gen=twin, show=fix[0]), USED_UP.format(gen=twin, show=fix[1])) == []
    assert refused(change(USED_UP.format(gen=bad, show=fix[0]), USED_UP.format(gen=bad, show=fix[1])), "print")


def test_accepts_iterators_used_up_where_they_stand():
    for e in ("'-'.join(x for x in answer)", "sum(len(x) for x in answer)", "sorted(zip(answer, answer))",
              "[i for i, v in enumerate(answer)]", "dict(zip(answer, answer))", "any(x for x in answer)"):
        assert change("", f"print({e})\n") == [], e
    assert change("", "for i, v in enumerate(answer):\n    print(i, v)\n") == []
    for e in ("(x for x in answer)", "zip(answer)", "[enumerate(answer)]", "answer.get('k', zip(answer))"):
        assert refused(change("", f"print({e})\n"), "print"), e


FILLED = "paths = []\n{mk}def fill(m):\n    for f in os.listdir('.'):\n        {fill}\nfill(m)\nfor p in paths:\n"


@pytest.mark.parametrize("head, mk, fill, twin", [
    ("import __main__\n", "", "__main__.paths.append(Path(f))", "print(f)"),     # review 6's trace: __main__
    ("", "", "m.paths.append(Path(f))", "m.other.append(Path(f))"),              # the name read through a namespace
    ("", "", "m.paths = [Path(f)]", "m.other = [Path(f)]"),                      # rebound through a namespace
    ("", "def mk():\n    return paths\n", "m.mk().append(Path(f))", "m.other().append(Path(f))"),  # returned to m.mk()
])
def test_refuses_container_filled_through_a_namespace(head, mk, fill, twin):
    """A module's own name reached as an attribute (``__main__.paths``, or ``m.paths`` of a namespace the guard cannot
    name) is read as that name, and ``import __main__`` is refused (review round 6). A name given only as a string to
    code the guard does not read (``operator.attrgetter('paths')``) is residual 5."""
    def fixed(f, h):
        prog = HEAD + h + FILLED.format(mk=mk, fill=f)
        return esc(prog + "    q = p\n", prog + "    q = p.replace('../../victim')\n")

    assert fixed(twin, "") == [], "the twin: the same fix, the container filled by nothing"
    why = fixed(fill, head)
    assert refused(why, "imports __main__" if head else "changed, line")


@pytest.mark.parametrize("deco", ["", "import functools\n@functools.cache\n"])
def test_refuses_module_function_call(deco):
    f = deco + "def parse(x):\n    return x\n"
    assert change(f, f + "print('a')\n") == []
    assert refused(change(f, f + "print(parse('a'))\n"), "print of shaped")


# ---- taint and control (G3, G4)


def test_taint_into_unchanged_call_refused():
    assert refused(change("cmd = 'ls'\nos.system(cmd)\n", "cmd = 'rm'\nos.system(cmd)\n"), "reading what the change made")
    assert change("cmd = 'ls'\nprint(cmd)\n", "cmd = 'rm'\nprint(cmd)\n") == []


def test_taint_through_function_return_refused():
    old = 'def f():\n    return "a"\nx = f()\n{last}\n'
    for last in ("os.remove(x)", "print(x)"):         # print(x) too: x, a module function's value, is not shaped
        assert refused(change(old.format(last=last), old.format(last=last).replace('"a"', '"b"')), "reading"), last
    last = "print('removing')\nos.remove('p')"         # the same call, its value used by nothing: accepted
    assert change(old.format(last=last), old.format(last=last).replace('"a"', '"b"')) == []


CFG = "class Cfg:\n    path = 'a'\n"
J = "class J:\n    def p(self):\n        return 'a'\n"
KEEP = "class I:\n    def keep(self, it):\n        return 'a' == 'a'\n"
REG = "REG = []\ndef reg(f):\n    REG.append(f)\n    return f\n{deco}def h():\n    return 'a'\n"


@pytest.mark.parametrize("prog, twin, why", [
    (CFG + "os.remove(Cfg.path)\n", CFG + "os.remove('a')\n", "Cfg holds the change"),
    (J + "j = J()\nos.remove(j.p())\n", J + "os.remove('a')\n", "reading what the change made"),
    (KEEP + "for it in answer:\n    if not I().keep(it):\n        os.remove(it)\n", KEEP + "os.remove('a')\n",
     "reading what the change made"),
    (REG.format(deco="@reg\n") + "for g in REG:\n    os.remove(g())\n", REG.format(deco="") + "os.remove('a')\n",
     "decorated"),
    (REG.format(deco="") + "REG.append(h)\nfor g in REG:\n    os.remove(g())\n",
     REG.format(deco="") + "os.remove('a')\n", "used other than by a call"),
])
def test_taint_through_attributes_and_registries_refused(prog, twin, why):
    """A value reaching unchanged code through an attribute (a class attribute, a method's return) or a function
    reached other than by a call (decorated, stored) is followed: refused. The same change that nothing reads: accepted."""
    assert change(twin, twin.replace("'a'", "'../x'", 1)) == []
    assert refused(change(prog, prog.replace("'a'", "'../x'", 1)), why)


FMETA = "def M(name, bases, ns):\n    for v in ns.values():\n        os.remove(v)\n    return type(name, bases, ns)\n"
CMETA = ("class Meta(type):\n    def __init__(cls, name, bases, ns):\n        for v in ns.values():\n"
         "            os.remove(v)\nclass Base(metaclass=Meta):\n    pass\n")
SUBREG = ("import operator\nREG = []\nclass Base:\n    def __init_subclass__(cls):\n        REG.append(cls)\n")
SUBUSE = ("for c in REG:\n    for k in dir(c):\n        if not k.startswith('_'):\n"
          "            os.remove(operator.attrgetter(k)(c))\n")


@pytest.mark.parametrize("head, bad, tail", [
    (FMETA, "class Cfg(metaclass=M):\n", ""),                    # a function metaclass, given the namespace
    (CMETA, "class Cfg(Base):\n", ""),                           # a class metaclass, through a base
    (SUBREG, "class Cfg(Base):\n", SUBUSE),                      # a base's __init_subclass__ registers it
    ("", "class Cfg[T]:\n", ""),                                 # a type parameter
])
def test_refuses_change_in_class_with_base_or_keyword(head, bad, tail):
    """Code in a class's header runs when the class is defined, with no call for G3 to follow: a class holding the
    change has no base, keyword or type parameter. The same class with none: accepted."""
    for cls, ok in ((bad, False), ("class Cfg:\n", True)):
        prog = head + cls + "    path = 'a'\n" + tail
        why = change(prog, prog.replace("'a'", "'../x'"))
        assert why == [] if ok else refused(why, "Cfg holds the change and has a base or keyword"), (cls, why)


def test_refuses_class_with_base_enclosing_the_change():
    prog = CMETA + "class Outer(Base):\n    class Cfg:\n        def p(self):\n            return 'a'\n"
    assert refused(change(prog, prog.replace("'a'", "'../x'")), "Outer holds the change and has a base or keyword")
    plain = prog.replace("class Outer(Base):", "class Outer:")
    assert change(plain, plain.replace("'a'", "'../x'")) == []


def test_accepts_augmented_assignment_of_a_shaped_name():
    """A name whose own binding reads it (``n += 1``) is shaped from its other bindings; a builtin's name is not."""
    assert change("n = 0\nn += 1\nprint(n)\n", "n = 0\nn += 2\nprint(n)\n") == []
    assert change("n = 0\nn = n + 1\n", "n = 0\nn = n + 2\n") == []
    assert refused(change("n = os.getpid()\nn += 1\n", "n = os.getpid()\nn += 2\n"), "not shaped")
    assert refused(change("n = n\n", "n = n\nprint(n)\n"), "print")           # nothing to start from
    assert refused(change("sum = 0\nsum += 1\n", "sum = 0\nsum += 2\n"), "not shaped")   # read finds the builtin


def test_refuses_type_parameter_shadowing_print():
    assert change("def f[T](x):\n    pass\n", "def f[T](x):\n    pass\nprint(1)\n") == []
    assert refused(change("def f[print](x):\n    pass\n", "def f[print](x):\n    pass\nprint(1)\n"), "print of shaped")


def test_tainted_for_iterable_body_must_pass():
    loop = "def send():\n    pass\nn = {n}\nfor _ in range(n):\n    send()\n"
    assert refused(change(loop.format(n=2), loop.format(n=3)), "steered by the change")
    loop = "n = {n}\nfor _ in range(n):\n    print('x')\n"
    assert change(loop.format(n=2), loop.format(n=3)) == []


def test_tainted_if_header_body_must_pass():
    prog = "p = 'f'\nflag = {v}\nif flag:\n    {body}\n"
    assert refused(change(prog.format(v=False, body="os.remove(p)"), prog.format(v=True, body="os.remove(p)")),
                   "steered by the change")
    assert change(prog.format(v=False, body="print(p)"), prog.format(v=True, body="print(p)")) == []


def test_removed_continue_controls_loop():
    prog = 'for it in answer["values"]:\n    if it["protected"]:\n        continue\n    {last}\n'
    base = BROKEN.split("for issue")[0]
    for last, ok in (('os.remove(it["path"])', False), ('print(it["path"])', True)):
        old = base + prog.format(last=last)
        new = old.replace('    if it["protected"]:\n        continue\n', "")
        assert (esc(old, new) == []) is ok, (last, esc(old, new))
    assert refused(esc(old.replace("print", "os.remove"), new.replace("print", "os.remove")), "steered by the change")


def test_removed_unreadable_statement_refused():
    base = "import sys\n" + BROKEN
    assert refused(change("sys.exit(0)\n", "", base=base), "removed, line", "expression other than")
    assert refused(change("def check(x):\n    pass\ncheck(answer)\n", "def check(x):\n    pass\n"), "removed, line",
                   "expression other than")
    assert change("print('x')\n", "", base=base) == []


def test_changed_raise_in_function_refused():
    assert refused(change("def f(x):\n    if x:\n        raise ValueError('a')\n",
                          "def f(x):\n    if x:\n        raise ValueError('b')\n"), "inside a function")
    assert change("if answer:\n    raise ValueError('a')\n", "if answer:\n    raise ValueError('b')\n") == []


def test_removed_return_controls_the_rest_of_the_function():
    f = "def f():\n    {r}os.remove('p')\nf()\n"
    assert refused(change(f.format(r="return\n    "), f.format(r="")), "steered")
    f = "def f():\n    {r}print('p')\nf()\n"
    assert change(f.format(r="return\n    "), f.format(r="")) == []


NAMES = "names = json.loads('[\"a\", \"b\"]')\n"


def test_break_taints_the_loop_target():
    loop = NAMES + "for p in names:\n    print('x')\n{b}{last}\n"
    steer = "if p == 'a':\n    os.remove('x')"                 # p stays shaped: only the taint of p refuses this
    for last, ok in (("os.remove(p)", False), (steer, False), ("os.remove('fixed')", True)):
        why = change(loop.format(b="", last=last), loop.format(b="    break\n", last=last))
        assert (why == []) is ok, (last, why)
    assert refused(change(loop.format(b="", last=steer), loop.format(b="    break\n", last=steer)), "steered by the change")
    # the simpler form: a loop over os.listdir left early changes which file the unchanged os.remove gets
    loop = "for p in os.listdir('.'):\n    print('x')\n{b}os.remove(p)\n"
    assert refused(change(loop.format(b=""), loop.format(b="    break\n")), "a for left early", "not shaped")


def test_break_over_a_shared_iterator_refused():
    tail = "it = (q for q in os.listdir('.'))\nfor q in it:\n    os.remove(q)\n"
    # the removing loop has a target of its own, so only how far ``it`` was used up is shared
    loop = "it = (f for f in os.listdir('.'))\nfor p in it:\n    print('seen')\n{b}for q in it:\n    os.remove(q)\n"
    assert refused(change(loop.format(b=""), loop.format(b="    break\n")), "a for left early", "not shaped")
    # the review's trace: the first loop shares ``it`` and ``p`` with the unchanged loop that removes files
    loop = loop.replace("for q in it:\n    os.remove(q)", "for p in it:\n    os.remove(p)")
    assert refused(change(loop.format(b=""), loop.format(b="    break\n")), "a for left early", "not shaped")
    # the twin: the loop left early is over a shaped list, and the removing loop has an iterator of its own
    loop = NAMES + "for p in names:\n    print('seen')\n{b}" + tail
    assert change(loop.format(b=""), loop.format(b="    break\n")) == []


def test_return_in_a_loop_in_a_function():
    f = "def first(xs):\n    for p in xs:\n        print('x')\n{r}it = (q for q in os.listdir('.'))\nfirst(it)\n"
    f += "for q in it:\n    os.remove(q)\n"
    assert refused(change(f.format(r=""), f.format(r="        return\n")), "a for left early", "not shaped")
    f = NAMES + "def first():\n    for p in names:\n        print('x')\n{r}first()\n{last}\n"
    for last, ok in (("os.remove(p)", False), ("if p == 'a':\n    os.remove('x')", False), ("os.remove('fixed')", True)):
        why = change(f.format(r="", last=last), f.format(r="        return\n", last=last))
        assert (why == []) is ok, (last, why)


# ---- G5


def test_change_inside_try_or_with_refused():
    assert refused(change("try:\n    v = 1\nexcept ValueError:\n    pass\n", "try:\n    v = 2\nexcept ValueError:\n    pass\n"),
                   "try or with")
    assert refused(change("with open('x') as f:\n    v = 1\n", "with open('x') as f:\n    v = 2\n"), "try or with")
    g = "def g():\n    v = {v}\n    return v\n"
    t = "try:\n    pass\nexcept ValueError:\n    pass\n"
    assert refused(change(g.format(v=1) + t, g.format(v=2) + t), "holds a try or with")
    assert change(g.format(v=1), g.format(v=2)) == []


# ---- residuals (SPEC §12r): what the guard does not see, as stated


def test_residual_implicit_raise_accepted():
    prog = "d = {{'k': 1}}\np = 'f'\nx = {x}\nos.remove(p)\n"
    assert change(prog.format(x="d.get('k')"), prog.format(x="d['k']")) == []


def test_residual_stdout_redirect_accepted():
    base = "import sys\n" + BROKEN + "sys.stdout = open('out', 'w')\n"
    assert change("print('a')\n", "print('b')\n", base=base) == []


def test_residual_other_modules_not_read():
    base = "import helper\n" + BROKEN                       # what helper does when imported is not seen
    assert change("print(len(answer))\n", "print(len(answer['values']))\n", base=base) == []
    # nor what another module's function does when called: here it rebinds json.loads, given its name as a string
    base = "from unittest import mock\nmock.patch('json.loads', os.system).start()\n" + BROKEN
    assert change("x = 1\n", "x = json.loads('ls')\n", base=base) == []


@pytest.mark.parametrize("gadget", [
    # the review's trace: a module's namespace reached and written through calls whose effect the guard does not read
    "import operator, sys\nns = operator.attrgetter('__dict__')(operator.attrgetter('modules')(sys)['builtins'])\n"
    "operator.setitem(ns, 'len', os.system)\n",
    "import timeit\ntimeit.timeit('import builtins, os; builtins.len = os.system', number=1)\n"])
def test_residual_own_code_rebinding_accepted(gadget):
    # (5): the program's own unchanged code may rebind a builtin, print or json by a call; the guard trusts it to not
    base = BROKEN + gadget
    assert change("print(len(answer))\n", "print(len(answer['values']))\n", base=base) == []


def test_residual_time_and_memory_accepted():
    assert change("", "big = 'x' * 10 ** 9\nfor i in range(10 ** 12):\n    pass\n") == []
