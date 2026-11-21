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


def test_residual_time_and_memory_accepted():
    assert change("", "big = 'x' * 10 ** 9\nfor i in range(10 ** 12):\n    pass\n") == []
