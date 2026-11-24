"""dev/records/model-split-oversized-systems.md: landing, times and intake split into named subsystems along their
clusters, nothing else changed. The model before the split is made again from the files (each new subsystem's
parts put back in its parent, the new systems taken out), so the comparison holds whatever the model gains later;
SPLIT pins which parts went where."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from ergostat.numbers.version import _plain, version
from ergostat.spec import read

ROOT = Path(__file__).resolve().parent.parent
NEW = {"merging": "landing", "upgrading": "landing", "switching": "landing",
       "state-times": "times", "loop-times": "times", "gate-times": "times",
       "open-gaps": "intake", "split-and-join": "intake"}
STATES = "open ready fix built approved queued replan planned split leased building in-review queue-failed dead"
# each subsystem's parts as split (main's landing, times and intake, along the clusters check found)
SPLIT = {
    "merging": "stock: gaps-approved gaps-queued gaps-queue-failed gaps-landed flakes-main-broken; flow: gaps-approved "
               "gaps-queued gaps-merged sent-back-by-queue queue-failures flakes-retried sent-back-by-triage "
               "parked-in-triage flakes-mended; auxiliary: batch-run-percent batch-run-failures push-waiting "
               "push-settleable main-stalled-minutes browser-main-green; goal: approved-gaps-landed "
               "queue-failures-triaged main-moving browser-main-green; block: queue-when merge-queue push-settler "
               "triage-when flake-triage browser-daily main-mend",
    "upgrading": "stock: upgrades-available; flow: upgrades-opened upgrades-installed upgrades-superseded; "
                 "goal: upgrades-taken-up; block: main-watch upgrader",
    "switching": "stock: upgrades-installed upgrades-approved upgrades-switching; flow: switches-approved "
                 "switches-withdrawn upgrades-switched upgrades-kept upgrades-reverted; goal: upgrades-switched-to; "
                 "block: approve-switch switcher switch",
    "state-times": "auxiliary: " + " ".join(f"in-{s}-hours in-{s}-hours-p90" for s in STATES.split())
                   + "; goal: ready-short queued-short replan-short planned-short leased-short queue-failed-short",
    "loop-times": "auxiliary: loop-hours loop-hours-p90 loop-rounds loop-rounds-p90 " + " ".join(
        f"gate-{g}-minutes gate-{g}-minutes-p90" for g in ("implementor", "fast", "review")) + "; goal: loop-short",
    "gate-times": "auxiliary: " + " ".join(f"gate-{g}-minutes gate-{g}-minutes-p90" for g in
                                           ("unit", "browser", "demo", "push-wait")),
    "times": "block: timer",
    "open-gaps": "stock: gaps-open; flow: gaps-closed gaps-found gaps-requested gaps-defined simplifications-requested "
                 "gaps-split-off; auxiliary: grooming-open dependency-problems splits-clean splits-covered "
                 "split-budgets-held split-joins split-overhead; goal: dependencies-sound open-gaps-planned; "
                 "block: groom-when groomer intake",
    "split-and-join": "stock: gaps-split gaps-joined; flow: replans-split-off splits-joined joins-covered joins-short "
                      "joins-parked splits-parked; block: split-watch join-judge",
}
TABLES = ("stocks", "flows", "auxiliaries", "parameters", "goals", "blocks", "items", "actions", "agents")
NAMES = "|".join(map(re.escape, NEW))


def unsplit(text: str) -> str:
    """A model file as it was before the split: the new systems' declarations out, their parts in the parent."""
    text = re.sub(rf"(?m)^systems:\n(?:  (?:{NAMES}):\n(?:    .*\n)*)+", "", text)
    return re.sub(rf"(?<=system: )({NAMES})(?![\w-])", lambda m: NEW[m.group(1)], text)


def factory_copy(where: Path, edit=lambda text: text) -> Path:
    """The factory's model in a folder of its own, each model file (and ergostat.yaml) passed through ``edit``."""
    (where / "dev" / "model").mkdir(parents=True)
    for x in (ROOT / "dev").iterdir():
        if x.name != "model":
            (where / "dev" / x.name).symlink_to(x)
    for x in (ROOT / "dev" / "model").iterdir():
        (where / "dev" / "model" / x.name).write_text(edit(x.read_text()))
    (where / "ergostat.yaml").write_text(edit((ROOT / "ergostat.yaml").read_text()))
    return where


def loaded(where: Path):
    spec, problems = read(where / "ergostat.yaml")
    assert [str(p) for p in problems if p.level == "error"] == []
    return spec


def test_the_split_moves_parts_between_systems_and_changes_nothing_else(tmp_path):
    """Done 1: against the model with the split undone, the same parts, flows and goals (and parameters, blocks,
    items, actions, agents), each as written but for its system, which is the system it was in or a new subsystem
    of it, and the dynamics' version the same. (That the undone model is main's as it was is a one-off comparison,
    in the record; where each part went is pinned by the next test.)"""
    now = loaded(factory_copy(tmp_path / "now"))
    before = loaded(factory_copy(tmp_path / "before", unsplit))
    assert set(NEW) <= set(now.systems) and not set(NEW) & set(before.systems)
    assert {s: now.within.get(s) for s in NEW} == NEW
    assert set(now.systems) - set(NEW) == set(before.systems)
    moved = Counter()
    for table in TABLES:
        a, b = getattr(before, table), getattr(now, table)
        assert set(a) == set(b), (table, set(a) ^ set(b))
        for name in a:
            was, got = _plain(a[name]), _plain(b[name])
            if isinstance(was, dict) and "system" in was:
                s0, s1 = was.pop("system"), got.pop("system")
                assert s1 == s0 or (s1 in NEW and NEW[s1] == s0), (table, name, s0, s1)
                moved[s1] += s1 != s0
            assert got == was, (table, name)
            assert getattr(a[name], "description", None) == getattr(b[name], "description", None), (table, name)
    assert version(now) == version(before)                 # the stocks, flows, equations and numbers: the same
    assert all(moved[s] for s in NEW), moved               # every new subsystem was given parts
    for parent in set(NEW.values()):                       # what was directly in landing, times or intake
        own = [f"{t}.{n}" for t in TABLES for n, x in getattr(before, t).items() if getattr(x, "system", None) == parent]
        assert own


@pytest.mark.slow
def test_ergostat_check_passes_on_the_split_model(tmp_path, capsys, monkeypatch):
    """Done 1: `ergostat check` passes on the factory's model as split. Landing and intake are no longer said to
    split (their clusters are their subsystems); what the split newly says is only of the new subsystems: the
    time scales inside switching (the coordinator's approval against the switch) and split-and-join (a split's
    wait against the join judge's), and split-and-join's blocks acting for no goal in it (no goal holds the joins)."""
    from ergostat.cli import main
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))

    def found(where: Path) -> set[str]:
        main(["-C", str(where), "check", "--json"])
        got = json.loads(capsys.readouterr().out)
        assert got["ok"], [x for x in got["found"] if x["level"] == "error"]
        return {x["id"] for x in got["found"]}
    now = found(factory_copy(tmp_path / "now"))
    before = found(factory_copy(tmp_path / "before", unsplit))
    assert {"system-splits@system.landing", "system-splits@system.intake"} <= before - now
    assert sorted(now - before) == ["purpose@system.split-and-join", "time-scales@system.split-and-join",
                                    "time-scales@system.switching"]


def test_each_subsystem_holds_the_parts_of_its_cluster():
    """The split as made: landing's 50 parts, times' 54 and intake's 29 (as on main before it), each in the
    subsystem of its cluster (a part added later may join one; none of these may leave it)."""
    from ergostat.spec import architecture as ar
    spec = loaded(ROOT)
    parts = ar._parts(spec)
    split = {s: {f"{k.strip()}.{n}" for group in text.split(";") for k, names in [group.split(":")]
                 for n in names.split()} for s, text in SPLIT.items()}
    assert [len(split[s]) for s in SPLIT] == [31, 7, 12, 34, 11, 8, 1, 19, 10]
    assert {p: parts.get(p) for s, ps in split.items() for p in ps if parts.get(p) != s} == {}


def test_no_system_has_more_than_40_parts():
    """Done 2: no system has more than 40 parts of its own (the redesign's MOST_PARTS), and none is too large to
    redesign: landing and times are taken a subsystem at a time, intake (under 40 in all) whole. Landing and
    intake are nearly decomposable, their well-separated clusters their subsystems."""
    from ergostat.numbers.redesign_due import MOST_PARTS, units
    from ergostat.spec import architecture as ar
    spec = loaded(ROOT)
    own = Counter(ar._parts(spec).values())
    assert MOST_PARTS == 40
    assert {s: n for s, n in own.items() if n > MOST_PARTS} == {}
    assert own["landing"] == own["intake"] == 0 and own["times"] == 1          # (the timer, which writes all three)
    assert all(own[s] for s in NEW)
    taken, big = units(spec)
    assert big == []
    assert {s for s, p in NEW.items() if p != "intake"} <= set(taken) and "intake" in taken
    assert not {"landing", "times", "open-gaps", "split-and-join"} & set(taken)
    for s in ("landing", "intake"):
        assert ar.nearly_decomposable(spec, s), s
