"""A quiet system says so (SPEC §8, a quiet system): every goal of it holding gives 'all N goals holding, nothing
being worked', or the items its blocks hold leases on; a goal off or unknown, and nothing is said."""

from ergostat import model as mdl
from ergostat import state
from ergostat.store import Project

N = 14
MODEL = "\n".join([
    "name: quiet", "systems:", "  shop: {}", "  yard: {}", "items:", "  job:", "    id: job/*",
    "    states: [waiting, done]", "    system: shop", "    on: {job.done: done}", "stocks:",
    *[f"  q{i}: {{unit: jobs, system: shop, sensor: {{run: echo 1, every: 1h}}}}" for i in range(1, N + 1)],
    "  pile: {unit: jobs, system: yard, sensor: {run: echo 1, every: 1h}}",
    "flows:", "  served: {from: q1, system: shop}", "  carted: {from: pile, system: yard}",
    *[f"  f{i}: {{from: q{i}, system: shop}}" for i in range(1, N + 1)],
    "goals:", *[f"  g{i}: {{stock: q{i}, hold: \"<= 5\", system: shop}}" for i in range(1, N + 1)],
    "  pile-small: {stock: pile, hold: \"<= 5\", system: yard}",
    "blocks:",
    *[f"  k{i}: {{type: onoff, goal: g{i}, out: block.a{i}, system: shop}}\n"
      f"  a{i}: {{type: program, run: \"true\", in: block.k{i}, out: flow.f{i}, system: shop}}" for i in range(1, N + 1)],
    "  kp: {type: onoff, goal: pile-small, out: block.ap, system: yard}",
    "  ap: {type: program, run: \"true\", in: block.kp, out: flow.carted, system: yard}",
    "  worker: {type: program, run: \"true\", takes: {kind: job, at: waiting, to: [done]}, out: flow.served, system: shop}",
    ""])
TAKEN = {"block": "worker", "ttl": 2400, "max": 2, "back": "waiting", "tier": "program"}


def seeded(tmp_path, monkeypatch, value=1.0, unread=()):
    """Every goal's sensor read at ``value`` (1: holding), but those of the stocks in ``unread``."""
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ergostat.yaml").write_text(MODEL)
    p = Project(mdl.load(repo / "ergostat.yaml"))
    for lp in p.model.loops():
        if lp.controller.holds not in unread:
            for s in lp.sensors:
                p.measurements.add(f"sensor/{s}", value if lp.controller.holds == "q2" else 1.0)
    return p


def take(p, *ids):
    for n, i in enumerate(ids, 1):
        p.events.add("job.queued", item=i)
        p.events.add("ergostat.lease.taken", item=i, data={**TAKEN, "run": f"run{n}aaaaaaaa", "fence": 1})


def test_every_goal_holding_says_so_with_the_count_the_loops_filtered_by_system_give(tmp_path, monkeypatch):
    p = seeded(tmp_path, monkeypatch)
    snap = state.snapshot(p)
    mine = [n for n, lp in snap["loops"].items() if lp["system"] == "shop"]
    assert len(mine) == N and all(snap["loops"][n]["status"] == "holding" for n in mine)
    assert state.quiet(p, snap, "shop") == f"all {len(mine)} goals holding, nothing being worked"
    assert state.quiet(p, snap, "yard") == "all 1 goal holding, nothing being worked"
    assert state.quiet(p, snap, "nowhere") is None                     # no goals: nothing to call holding


def test_the_items_leased_in_it_are_the_count_being_worked(tmp_path, monkeypatch):
    p = seeded(tmp_path, monkeypatch)
    take(p, "job/1", "job/2", "job/3")
    snap = state.snapshot(p)
    assert state.quiet(p, snap, "shop") == f"all {N} goals holding, 3 items being worked"
    assert state.quiet(p, snap, "yard") == "all 1 goal holding, nothing being worked"   # not its block's leases
    p.events.add("ergostat.lease.ended", item="job/3", data={"run": "run3aaaaaaaa", "fence": 1, "how": "nack", "count": False})
    assert state.quiet(p, state.snapshot(p), "shop") == f"all {N} goals holding, 2 items being worked"


def test_one_unknown_goal_and_it_says_nothing(tmp_path, monkeypatch):
    p = seeded(tmp_path, monkeypatch, unread=("q7",))
    snap = state.snapshot(p)
    assert snap["loops"]["g7"]["status"] == "unknown"
    assert state.quiet(p, snap, "shop") is None
    assert state.quiet(p, snap, "yard") is not None


WHERE = (("a", "plant"), ("b", "line"), ("c", "line"))
NESTED = "\n".join([
    "name: nested", "systems:", "  plant: {}", "  line: {within: plant}", "items:", "  job:", "    id: job/*",
    "    states: [waiting, done]", "    system: line", "    on: {job.done: done}", "stocks:",
    *[f"  {s}: {{unit: jobs, system: {y}, sensor: {{run: echo 1, every: 1h}}}}" for s, y in WHERE],
    "flows:", "  served: {from: b, system: line}", *[f"  f{s}: {{from: {s}, system: {y}}}" for s, y in WHERE],
    "goals:", *[f"  g{s}: {{stock: {s}, hold: \"<= 5\", system: {y}}}" for s, y in WHERE],
    "blocks:", *[f"  k{s}: {{type: onoff, goal: g{s}, out: block.a{s}, system: {y}}}\n"
                 f"  a{s}: {{type: program, run: \"true\", in: block.k{s}, out: flow.f{s}, system: {y}}}" for s, y in WHERE],
    "  worker: {type: program, run: \"true\", takes: {kind: job, at: waiting, to: [done]}, out: flow.served, system: line}",
    ""])


def nested(tmp_path, monkeypatch, read):
    """The plant holding its own goal ga, and the line within it holding gb and gc; ``read`` each stock's reading."""
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "ergostat.yaml").write_text(NESTED)
    p = Project(mdl.load(repo / "ergostat.yaml"))
    for lp in p.model.loops():
        if read.get(lp.controller.holds) is not None:
            for s in lp.sensors:
                p.measurements.add(f"sensor/{s}", read[lp.controller.holds])
    return p


def test_a_system_is_quiet_only_when_the_systems_within_it_are(tmp_path, monkeypatch):
    p = nested(tmp_path / "1", monkeypatch, {"a": 1.0, "b": 1.0, "c": 1.0})
    take(p, "job/1")
    snap = state.snapshot(p)
    assert state.quiet(p, snap, "line") == "all 2 goals holding, 1 item being worked"
    assert state.quiet(p, snap, "plant") == "all 3 goals holding, 1 item being worked"   # its box folds the line in
    p = nested(tmp_path / "2", monkeypatch, {"a": 1.0, "b": 1e6, "c": 1.0})
    snap = state.snapshot(p)
    assert snap["loops"]["gb"]["status"] == "off"
    assert state.quiet(p, snap, "plant") is None and state.quiet(p, snap, "line") is None
    p = nested(tmp_path / "3", monkeypatch, {"a": 1.0, "b": 1.0})
    snap = state.snapshot(p)
    assert snap["loops"]["gc"]["status"] == "unknown"
    assert state.quiet(p, snap, "plant") is None and state.quiet(p, snap, "line") is None


def test_one_goal_off_and_it_says_nothing(tmp_path, monkeypatch):
    p = seeded(tmp_path, monkeypatch, value=1e6)
    snap = state.snapshot(p)
    assert snap["loops"]["g2"]["status"] == "off"
    assert state.quiet(p, snap, "shop") is None
