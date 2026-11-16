"""A stand-in developer: takes the most urgent ticket and changes textkit for it, the way a
developer who mostly gets it right would. It reads what the ticket says, then writes the
operation. Its mistakes are on purpose, and tunable:

    FACTORY_DEV_QUALITY   the chance it gets the operation right (default 0.75): otherwise it
                          misses a case the ticket's examples do not show (input with digits)
    FACTORY_DEV_CARELESS  the chance it also "tidies" a helper other operations share and breaks
                          them (default 0.1): a regression, unless review or the tests catch it
    FACTORY_PACE          seconds it takes (default 3)

(It knows the right answer from the world's truth, which a real developer would not: it stands in
for the ticket's description and examples being enough. FACTORY_AI=claude is the real thing.)"""

import inspect
import os
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "bin"), str(ROOT / "world")]
import factory  # noqa: E402
import oracle  # noqa: E402

sys.stdin.read()                                         # the prompt and the block's input: the ticket is what matters
me = os.environ.get("ERGOSTAT_BLOCK", "developer")
t = factory.claim(me)
if t is None:
    print("nothing open", file=sys.stderr)
    factory.moved("submitted", 0)
    raise SystemExit(0)
rng = random.Random()
time.sleep(float(os.environ.get("FACTORY_PACE", "3")))
wd = Path(t["workdir"])
src = (wd / "textkit.py").read_text()
op = t["op"]
code = inspect.getsource(oracle.BY_NAME[op])
right = rng.random() < float(os.environ.get("FACTORY_DEV_QUALITY", "0.75"))
if not right:                                            # works on the ticket's examples; not when there are digits
    head, body = code.split("\n", 1)
    code = head + "\n    if any(c.isdigit() for c in text):\n        text = text.replace(' ', '')\n" + body
for mod in ("re", "string"):
    if f"{mod}." in code and f"\nimport {mod}\n" not in src:      # after the module's docstring
        end = src.index('"""', 3) + 3 if src.startswith('"""') else 0
        src = src[:end] + f"\n\nimport {mod}" + src[end:]
pat = re.compile(rf"^def {op}\(.*?(?=^def |\Z)", re.S | re.M)
src = pat.sub(code + "\n\n", src) if pat.search(src) else src.rstrip() + "\n\n\n" + code
careless = rng.random() < float(os.environ.get("FACTORY_DEV_CARELESS", "0.1"))
if careless:
    src = re.sub(r"def _words\(text\):\n    return .*\n", "def _words(text):\n    return text.strip().split(' ')\n", src)
(wd / "textkit.py").write_text(src)
ex = (t.get("examples") or t.get("failures") or [None])[0]
if ex and "expected" in ex and rng.random() < 0.7:
    tests = (wd / "test_textkit.py").read_text()
    n = len(re.findall(r"^def test_", tests, re.M))
    tests = tests.replace('\n\nif __name__ == "__main__":', f"\n\ndef test_{op}_{n}():\n    assert textkit.{op}({ex['input']!r}) == "
                          f"{ex['expected']!r}\n\n\nif __name__ == \"__main__\":")
    (wd / "test_textkit.py").write_text(tests)
note = f"{op}: {'implemented' if t['type'] == 'feature' else 'fixed'}" + (" (and tidied _words)" if careless else "")
print(f"{t['ticket']}: {note}; {'right' if right else 'misses digits'}", file=sys.stderr)
factory.moved("submitted", 1 if factory.submit(t["ticket"], note, me) else 0)
