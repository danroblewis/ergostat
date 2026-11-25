"""The modelling loop as a template (SPEC §2a, §12e): ``use: modelling`` expands to exactly the loop the examples
wired by hand (the fixture, the-job's file before it), its parts keep their names, it is used once a model, a system
the model declares under its name is the model's, and with nothing given it runs on a free stand-in improver."""

import dataclasses
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from ergostat.spec import read
from ergostat.spec.causal import loops as causal_loops

FIXTURE = Path(__file__).parent / "fixtures" / "modelling-hand-wired.yaml"
MAIN = """
name: t
include: [modelling.yaml]
systems:
  modelling:
    description: the model, improved by a loop of its own
    show: [stock.model-error, stock.pending-changes]
"""
USE = """
uses:
  modelling:
    use: modelling
    with:
      fit: 0.05
      prompt: prompts/improver.md
      run: python3 bin/improver.py
      sessions: true
      hold-out: 4m
      windows: [1, 2, 4]
      threshold: 2%
      accept:
        parameter: auto
"""


def norm(x):
    """A part as plain data, without where it was written."""
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {f.name: norm(getattr(x, f.name)) for f in dataclasses.fields(x) if f.name not in ("where", "wheres", "defined")}
    if isinstance(x, dict):
        return {str(k): norm(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [norm(v) for v in x]
    if isinstance(x, set | frozenset):
        return sorted((norm(v) for v in x), key=json.dumps)
    return x if isinstance(x, int | float | str | bool) or x is None else str(x)


def model(tmp_path: Path, modelling: str):
    (tmp_path / "prompts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompts" / "improver.md").write_text("review the model\n")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MAIN))
    (tmp_path / "modelling.yaml").write_text(textwrap.dedent(modelling))
    spec, ps = read(tmp_path / "ergostat.yaml")
    assert not [p for p in ps if p.level == "error"], [str(p) for p in ps if p.level == "error"]
    return spec, ps


def parts(spec) -> dict:
    out = {s: {n: norm(v) for n, v in getattr(spec, s).items()} for s in ("stocks", "flows", "goals", "blocks", "auxiliaries")}
    out["items"] = {n: norm(v) for n, v in spec.items.items()}
    out |= {"systems": spec.systems, "within": spec.within, "show": norm(spec.show), "improve": norm(spec.improve),
            "loops": sorted(json.dumps(norm(x)) for x in spec.loops()),
            "causal": sorted(json.dumps(norm(x)) for x in causal_loops(spec))}
    return out


def test_it_expands_to_exactly_the_loop_the_examples_wired_by_hand(tmp_path):
    hand, hps = model(tmp_path / "hand", FIXTURE.read_text())
    used, ups = model(tmp_path / "used", USE)
    a, b = parts(hand), parts(used)
    new = {"stocks": {"unanswered-requests", "answered-requests"}, "goals": {"requests-handled"},
           "blocks": {"fixer", "keep-requests-handled"},
           "flows": {"changes-made-by-fixer", "requests-raised", "requests-answered"}}
    for k in ("stocks", "flows", "goals", "blocks", "auxiliaries"):   # the hand-wired loop, and the requests and the rule tier
        assert set(b[k]) - set(a[k]) == new.get(k, set()), k
        for n in a[k]:
            if n == "changes-made":                    # now the improver's and ergostat's finders' (the tiers have their own)
                continue
            got = {f: v for f, v in b[k][n].items() if f != "description"}
            want = {f: v for f, v in a[k][n].items() if f != "description"}
            assert got == want, (k, n)
    assert a["improve"]["accept"]["parameter"] == b["improve"]["accept"]["parameter"] == "auto"
    assert sorted(f"{p.code} {p.about}" for p in hps if p.level != "note") == \
        sorted(f"{p.code} {p.about}" for p in ups if p.level != "note")
    assert used.uses["modelling"]["template"] == "modelling"
    assert used.blocks["improver"].where.line == used.stocks["model-error"].where.line   # every part points at use:


def test_with_nothing_given_it_closes_its_loop_on_a_free_stand_in(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: t\nuses:\n  modelling:\n    use: modelling\n")
    spec, ps = read(tmp_path / "ergostat.yaml")
    assert not [p for p in ps if p.level == "error"], [str(p) for p in ps if p.level == "error"]
    assert not [p for p in ps if p.code == "missing-feedback"]
    assert {"model-error", "pending-changes", "accepted-changes"} <= set(spec.stocks)
    b = spec.blocks["improver"]
    assert b.type == "ai" and "standin improver" in b.params["run"] and Path(b.params["prompt"]).is_file()
    assert spec.blocks["judge"].type == "judge" and set(spec.improve.accept.values()) == {"owner"}   # nothing automatic
    assert "modelling" in spec.systems and spec.items["session"].formats == {"transcript": "claude-session"}   # the built-in session kind
    assert any(p.code == "template-stand-in" for p in ps)


def test_an_empty_run_gives_the_prompt_to_claude_and_a_person_may_improve(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: t\nuses:\n  modelling:\n    use: modelling\n    with: {run: '', model: sonnet}\n")
    spec, _ = read(tmp_path / "ergostat.yaml")
    assert "run" not in spec.blocks["improver"].params and spec.blocks["improver"].params["model"] == "sonnet"
    (tmp_path / "ergostat.yaml").write_text("name: t\nuses:\n  modelling:\n    use: modelling\n    with: {rung: person}\n")
    spec, ps = read(tmp_path / "ergostat.yaml")
    assert "improver" not in spec.blocks and spec.blocks["improver-by-hand"].type == "person"
    assert not [p for p in ps if p.level == "error"]


def test_it_is_used_once_a_model(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: t\nuses:\n  modelling: {use: modelling}\n  again: {use: modelling}\n")
    _, ps = read(tmp_path / "ergostat.yaml")
    assert any(p.code == "used-twice" and "once a model" in p.message for p in ps)


def test_a_system_the_model_declares_under_its_name_is_the_models_wherever_it_is_written(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: t\ninclude: [later.yaml]\nuses:\n  modelling: {use: modelling}\n")
    (tmp_path / "later.yaml").write_text("systems:\n  modelling:\n    description: mine\n")
    spec, ps = read(tmp_path / "ergostat.yaml")
    assert not [p for p in ps if p.level == "error"], [str(p) for p in ps if p.level == "error"]
    assert spec.systems["modelling"] == "mine" and spec.stocks["model-error"].system == "modelling"


def test_the_stand_in_improver_asks_ergostats_finders_and_proposes_nothing(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: t\nuses:\n  modelling: {use: modelling}\n")
    fake = tmp_path / "fake.py"
    fake.write_text("import sys, json\nopen(sys.argv[1], 'w').write(' '.join(sys.argv[2:]))\nprint(json.dumps([{'id': 'x'}]))\n")
    said = tmp_path / "said"
    p = subprocess.run([sys.executable, "-m", "ergostat.library.run", "standin", "improver"], cwd=tmp_path, input="prompt",
                       capture_output=True, text=True, timeout=60,
                       env={**os.environ, "ERGOSTAT_CMD": f"{sys.executable} {fake} {said}"})
    assert p.returncode == 0, p.stderr
    assert said.read_text() == "proposals --json"
    assert "propose" not in p.stdout and "1 change" in p.stderr
