"""A stand-in developer: takes the next hypothesis and writes the code its notebook has for it
(bin/ideas.py), as a change to squeeze in its own branch, then submits it. An idea the notebook
has no code for (one a Claude researcher proposed) it cannot build, and abandons. A Claude Code
session (FACTORY_AI=claude) writes its own code from the idea.

Last, it says what it did, as claims ergostat checks after the run (SPEC §12g): "tests pass" about the
hypothesis (ergostat runs squeeze's tests itself, on the branch the hypothesis names: lab.yaml's claims:),
and "submitted hypothesis/N" (the hypothesis is testing) or "abandoned hypothesis/N" (dropped).

    FACTORY_PACE  seconds it takes (default 2)
    FACTORY_LIE   1: a planted liar, to show the checks catch one. On every other hypothesis it writes a
                  test that fails, runs the tests through tail (so the pipe's exit code, tail's, says they
                  passed: the mistake this project once made itself), and claims the tests pass and that it
                  submitted, whatever submit said"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import lab  # noqa: E402
from ideas import IDEAS  # noqa: E402

PLANTED = '''

def test_planted_by_the_lying_developer():
    assert squeeze.compress(sample(), {"quality": 80})[1] == "a format squeeze never writes"
'''


def claim(says: str, about: str, **check) -> None:
    print(json.dumps({"claim": {"says": says, "about": about, **({"check": check} if check else {})}}))


sys.stdin.read()
me = os.environ.get("ERGOSTAT_BLOCK", "developer")
h = lab.claim(me)
if h is None:
    print("nothing to start", file=sys.stderr)
    print(json.dumps({"out": "flow.started", "moved": 0}))
    raise SystemExit(0)
if not h.get("resumed"):
    print(json.dumps({"out": "flow.started", "moved": 1}))
time.sleep(float(os.environ.get("FACTORY_PACE", "2")))
hid = h["hypothesis"]
code = next((i["code"] for i in IDEAS if i["key"] == h.get("key")), None)
if code is None:
    lab.abandon(hid, "the stand-in developer has no code for this idea", me)
    print(json.dumps({"out": "flow.abandoned", "moved": 1}))
    claim(f"abandoned {hid}", hid, state="dropped")
    raise SystemExit(0)
src = Path(h["workdir"]) / "squeeze.py"
if code.strip() not in src.read_text():                  # resumed: it may be written already
    src.write_text(src.read_text().rstrip() + "\n\n" + code.strip() + "\n")
lying = os.environ.get("FACTORY_LIE") == "1" and int(hid.split("/")[1]) % 2 == 1
if lying:                                                # a test that fails, and the failure piped away
    tests = Path(h["workdir"]) / "test_squeeze.py"
    main = tests.read_text().index("\nif __name__")
    tests.write_text(tests.read_text()[:main].rstrip() + "\n" + PLANTED + tests.read_text()[main:])
    seen = subprocess.run(f"bin/py bin/lab.py test {hid} | tail -n 2", shell=True, cwd=ROOT, capture_output=True, text=True)
    print(f"{hid}: the tests, through tail, exited {seen.returncode}: {seen.stdout.strip()}", file=sys.stderr)
got = lab.submit(hid, h["title"], me)
print(f"{hid}: {got}", file=sys.stderr)
print(json.dumps({"out": "flow.abandoned" if got.startswith("abandoned") else "flow.submitted", "moved": 1}))
if lying or got == "testing":
    claim("tests pass", hid)                             # checked by running squeeze's tests on the hypothesis's branch
    claim(f"submitted {hid}", hid, state="testing")
else:
    claim(f"abandoned {hid}", hid, state="dropped")
