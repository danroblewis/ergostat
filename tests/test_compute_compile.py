"""compute: pools in the model (SPEC §12k, *Compute pools*): what a pool compiles to, each refusal with its code and
its place, the ceilings at and past their edge, and a model without compute: compiling as it did."""

import dataclasses
import textwrap

import pytest

from ergostat import spec as sp
from ergostat.numbers.version import _plain, version

BASE = """\
name: t
stocks:
  queue: {unit: items}
blocks:
  build: {type: program, run: "true", every: 1h}
"""


def read(tmp_path, compute: str = ""):
    f = tmp_path / "ergostat.yaml"
    f.write_text(BASE + ("compute:\n" + textwrap.indent(textwrap.dedent(compute), "  ") if compute else ""))
    s, problems = sp.read(f)
    return s, [p for p in problems if p.level == "error"], f.read_text().splitlines()


def nodes(n: int) -> str:
    return "nodes: [" + ", ".join(f"{{ssh: node-{i}}}" for i in range(n)) + "]"


def test_a_pool_compiles_into_the_model_with_bytes_and_seconds(tmp_path):
    s, errors, _ = read(tmp_path, """
        farm:
          nodes: [{ssh: node-1}, {ssh: build.lan}, {connect: [ergostat, worker, --stdio]}]
          backend: docker
          image: ergostat-run:1
          slots: 4
          limits: {cpus: 2, memory: 4g, pids: 512, disk: 10GiB, wall: 30m, network: none, log: 1g}
          repos: {main-repo: .}
          secrets: {API_TOKEN: ~/.config/ergostat/api.token}
          labels: {arch: x86_64}
        small:
          nodes: [{ssh: node-9}]
    """)
    assert errors == []
    p = s.compute["farm"]
    assert p.nodes == [{"ssh": "node-1"}, {"ssh": "build.lan"}, {"connect": ["ergostat", "worker", "--stdio"]}]
    assert (p.backend, p.image, p.slots) == ("docker", "ergostat-run:1", 4)
    assert p.limits == {"cpus": 2.0, "memory": 4 << 30, "pids": 512, "disk": 10 << 30, "wall": 1800.0,
                        "network": "none", "log": 1 << 30}
    assert (p.repos, p.secrets, p.labels) == ({"main-repo": "."}, {"API_TOKEN": "~/.config/ergostat/api.token"},
                                              {"arch": "x86_64"})
    q = s.compute["small"]
    assert (q.backend, q.image, q.slots, q.limits) == ("process", None, 1, {"log": 64 << 20})


def test_a_model_without_compute_compiles_to_an_identical_ir(tmp_path):
    a, errors, _ = read(tmp_path)
    assert errors == [] and a.compute == {}
    b, errors, _ = read(tmp_path, "farm: {nodes: [{ssh: node-1}], slots: 2}")
    assert errors == [] and set(b.compute) == {"farm"}
    for f in dataclasses.fields(a):
        if f.name != "compute":
            assert _plain(getattr(a, f.name)) == _plain(getattr(b, f.name)), f.name
    assert version(a) == version(b)


REFUSALS = [
    ("unknown-key", "farm:\n  nodes: [{ssh: n}]\n  colour: red", "colour"),
    ("unknown-key", "farm:\n  nodes: [{ssh: n}]\n  limits:\n    colours: 3", "colours"),
    ("bad-size", "farm:\n  nodes: [{ssh: n}]\n  limits:\n    memory: 4 gigs", "memory"),
    ("bad-size", "farm:\n  nodes: [{ssh: n}]\n  limits:\n    disk: 0g", "disk"),
    ("bad-duration", "farm:\n  nodes: [{ssh: n}]\n  limits:\n    wall: soon", "wall"),
    ("too-many-nodes", f"farm:\n  {nodes(65)}", "nodes"),
    ("too-many-nodes", f"a:\n  {nodes(40)}\nb:\n  {nodes(40)}", "nodes"),
    ("too-many-slots", "farm:\n  nodes: [{ssh: n}]\n  slots: 65", "slots"),
    ("too-many-runs", f"farm:\n  {nodes(8)}\n  slots: 33", "nodes"),
    ("too-many-runs", f"a:\n  {nodes(4)}\n  slots: 40\nb:\n  {nodes(4)}\n  slots: 30", "nodes"),
    ("wall-over-a-day", "farm:\n  nodes: [{ssh: n}]\n  limits:\n    wall: 25h", "wall"),
    ("wall-over-a-day", "farm:\n  nodes: [{ssh: n}]\n  limits:\n    wall: .nan", "wall"),
    ("log-over-cap", "farm:\n  nodes: [{ssh: n}]\n  limits:\n    log: 2g", "log"),
    ("network-on-process", "farm:\n  nodes: [{ssh: n}]\n  limits:\n    network: none", "network"),
    ("docker-needs-image", "farm:\n  backend: docker\n  nodes: [{ssh: n}]", "backend"),
    ("node-names-user", "farm:\n  nodes:\n    - ssh: me@node-1", "me@node-1"),
    ("node-names-address", "farm:\n  nodes:\n    - ssh: 10.0.0.5", "10.0.0.5"),
    ("node-names-address", "farm:\n  nodes:\n    - ssh: node-1:2222", "node-1:2222"),
    ("node-names-address", "farm:\n  nodes:\n    - ssh: '::1'", "::1"),
    ("bad-node", "farm:\n  nodes:\n    - ssh: -oProxyCommand=sh", "-oProxyCommand"),
    ("bad-node", "farm:\n  nodes:\n    - {ssh: a, connect: [b]}", "connect"),
    ("bad-node", "farm:\n  nodes:\n    - connect: ergostat worker", "connect"),
    ("missing-key", "farm:\n  slots: 2", "slots"),
    ("bad-backend", "farm:\n  nodes: [{ssh: n}]\n  backend: kubernetes", "backend"),
    ("bad-number", "farm:\n  nodes: [{ssh: n}]\n  slots: 0", "slots"),
    ("bad-number", "farm:\n  nodes: [{ssh: n}]\n  limits:\n    cpus: .inf", "cpus"),
    ("bad-network", "farm:\n  nodes: [{ssh: n}]\n  backend: docker\n  image: i\n  limits:\n    network: lan", "network"),
    ("bad-secrets", "farm:\n  nodes: [{ssh: n}]\n  secrets:\n    api-token: f", "secrets"),
    ("bad-size", "farm:\n  nodes: [{ssh: n}]\n  limits:\n    log: lots", "log"),
    ("bad-size", "farm:\n  nodes: [{ssh: n}]\n  limits:\n    memory: '" + "9" * 400 + "'", "memory"),   # inf
    ("bad-size", "farm:\n  nodes: [{ssh: n}]\n  limits:\n    disk: " + "9" * 300 + "t", "disk"),     # inf by its unit
    ("not-a-map", "farm:\n  nodes: [{ssh: n}]\n  limits: 3", "limits"),
    ("bad-image", "farm:\n  nodes: [{ssh: n}]\n  backend: docker\n  image: ''", "image"),
    ("bad-repos", "farm:\n  nodes: [{ssh: n}]\n  repos:\n    Main: .", "repos"),
    ("bad-labels", "farm:\n  nodes: [{ssh: n}]\n  labels:\n    arch: ''", "labels"),
    ("bad-node", "farm:\n  nodes:\n    - ssh: \"node-1\\n\"", "node-1"),                       # `$` before a newline
    ("bad-secrets", "farm:\n  nodes: [{ssh: n}]\n  secrets:\n    \"API_TOKEN\\n\": f", "secrets"),
    ("bad-labels", "farm:\n  nodes: [{ssh: n}]\n  labels:\n    \"arch\\n\": x", "labels"),
    ("bad-backend", "farm:\n  nodes: [{ssh: n}]\n  backend: false", "backend"),             # not read as process
    ("bad-backend", "farm:\n  nodes: [{ssh: n}]\n  backend: ''", "backend"),
]


@pytest.mark.parametrize("code,body,marker", REFUSALS, ids=[f"{c}-{i}" for i, (c, _, _) in enumerate(REFUSALS)])
def test_each_refusal_has_its_code_and_its_place(tmp_path, code, body, marker):
    _, errors, lines = read(tmp_path, body)
    got = [e for e in errors if e.code == code]
    assert got, [(e.code, e.message) for e in errors]
    assert all(e.where is not None and marker in lines[e.where.line - 1] for e in got), \
        [(str(e.where), e.message) for e in got]


def test_a_template_cannot_declare_a_pool(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "farm.yaml").write_text("template: farm\ncompute:\n  farm: {nodes: [{ssh: n}]}\n")
    f = tmp_path / "ergostat.yaml"
    f.write_text(BASE + "library: {folder: lib, trust: owner}\nuses:\n  f: {use: farm}\n")
    s, problems = sp.read(f)
    assert s.compute == {}
    assert any("unknown section 'compute'" in p.message for p in problems if p.level == "error"), [(p.code, p.message) for p in problems]


FARM = "compute:\n  farm: {nodes: [{ssh: node-1}]}\n"


def runs(tmp_path, blocks: str, rest: str = FARM, stocks: str = "  queue: {unit: items}\n"):
    """A model of ``blocks:`` (indented two), a stock or two, and the farm pool: its spec, errors and lines."""
    f = tmp_path / "ergostat.yaml"
    f.write_text(f"name: t\nstocks:\n{stocks}blocks:\n{blocks}{rest}")
    s, problems = sp.read(f)
    return s, [p for p in problems if p.level == "error"], f.read_text().splitlines()


def test_runs_on_names_the_blocks_pool(tmp_path):
    s, errors, _ = runs(tmp_path, '  build: {type: program, run: "make all", every: 1h, runs-on: farm}\n'
                                  '  here: {type: program, run: "true", every: 1h, runs-on: local}\n')
    assert errors == []
    assert (s.blocks["build"].runs_on, s.blocks["here"].runs_on) == ("farm", None)


def test_runs_on_local_or_none_compiles_to_an_identical_ir(tmp_path):
    from ergostat.numbers import version as v
    got = []
    for say in ("", ", runs-on: local"):
        s, errors, _ = runs(tmp_path, f'  build: {{type: program, run: "true", every: 1h{say}}}\n')
        assert errors == []
        got.append(s)
    a, b = got
    for f in dataclasses.fields(a):
        assert _plain(getattr(a, f.name)) == _plain(getattr(b, f.name)), f.name
    assert "runs_on" not in _plain(a.blocks["build"])          # hashed as before the key existed
    assert (v.whole(a), v.part(a, "block.build")) == (v.whole(b), v.part(b, "block.build"))
    c, _, _ = runs(tmp_path, '  build: {type: program, run: "true", every: 1h, runs-on: farm}\n')
    assert v.whole(c) != v.whole(a) and v.changed_control(a, c) == ["block.build"]   # naming a pool is a change


SCRIPTED = "  build: {type: program, run: ./go.sh, every: 1h, runs-on: farm}\n"
RUNS_ON_REFUSALS = [
    ("unknown-pool", '  build: {type: program, run: "true", every: 1h, runs-on: frm}\n', "frm"),
    ("bad-runs-on", '  build: {type: program, run: "true", every: 1h, runs-on: [farm]}\n', "runs-on"),
    ("bad-runs-on", '  build: {type: program, run: "true", every: 1h, runs-on: Farm}\n', "Farm"),
    ("runs-on-ai", "  think: {type: ai, prompt: decide, every: 1h, runs-on: farm}\n", "runs-on"),
    ("runs-on-person", "  ask: {type: person, ask: decide, every: 1h, runs-on: farm}\n", "runs-on"),
    ("runs-on-daemon", "  serve: {type: program, daemon: srv, every: 1h, runs-on: farm}\n", "runs-on"),
    ("runs-on-calls", '  build: {type: program, run: "$ERGOSTAT_CMD event --add x", every: 1h, runs-on: farm}\n', "runs-on"),
    ("runs-on-calls", '  build: {type: program, run: "nc -U $ERGOSTAT_SOCKET", every: 1h, runs-on: farm}\n', "runs-on"),
    ("runs-on-calls", '  build: {type: program, run: "ergostat item x", every: 1h, runs-on: farm}\n', "runs-on"),
    ("runs-on-calls", SCRIPTED, "runs-on"),                                   # go.sh calls, written below
]


@pytest.mark.parametrize("code,blocks,marker", RUNS_ON_REFUSALS,
                         ids=[f"{c}-{i}" for i, (c, _, _) in enumerate(RUNS_ON_REFUSALS)])
def test_each_runs_on_refusal_has_its_code_and_its_place(tmp_path, code, blocks, marker):
    (tmp_path / "go.sh").write_text("#!/bin/sh\nmake\n\"$ERGOSTAT_CMD\" event --add built\n")
    s, errors, lines = runs(tmp_path, blocks)
    got = [e for e in errors if e.code == code]
    assert got, [(e.code, e.message) for e in errors]
    assert all(e.where is not None and marker in lines[e.where.line - 1] for e in got), \
        [(str(e.where), e.message) for e in got]
    assert code == "unknown-pool" or all(b.runs_on is None for b in s.blocks.values())   # refused at its key: not kept


def test_runs_on_a_sensor_is_refused_at_its_key(tmp_path):
    _, errors, lines = runs(tmp_path, '  build: {type: program, run: "true", every: 1h}\n', stocks=(
        "  queue:\n    unit: items\n    sensor:\n      run: echo 1\n      every: 1m\n      runs-on: farm\n"))
    got = [e for e in errors if e.code == "runs-on-sensor"]
    assert got and "runs-on" in lines[got[0].where.line - 1], [(e.code, e.message) for e in errors]


def test_a_script_is_read_for_calls(tmp_path):
    (tmp_path / "go.sh").write_text("#!/bin/sh\nmake  # ergostat-run images are built elsewhere\n")
    s, errors, _ = runs(tmp_path, SCRIPTED)
    assert errors == [] and s.blocks["build"].runs_on == "farm"               # no call in it: allowed
    (tmp_path / "go.sh").write_bytes(b"#" * (8 << 20) + b"\n")
    _, errors, _ = runs(tmp_path, SCRIPTED)
    assert [e.code for e in errors] == ["runs-on-calls"]                        # too large to read whole: as calling
    (tmp_path / "go.sh").write_text("#!/bin/sh\nexec ergostat\n")
    _, errors, _ = runs(tmp_path, SCRIPTED)
    assert [e.code for e in errors] == ["runs-on-calls"]                        # ergostat at the line's end


def test_a_file_outside_the_model_folder_is_not_read_for_calls(tmp_path):
    model, out = tmp_path / "model", tmp_path / "bin"
    model.mkdir(), out.mkdir()
    (out / "node").write_bytes(b"#" * (8 << 20) + b"\nexec ergostat\n")      # large, and calling: never read
    (model / "link.sh").symlink_to(out / "node")
    for run in (f"{out / 'node'} build.js", "../bin/node build.js", "./link.sh"):
        s, errors, _ = runs(model, f'  build: {{type: program, run: "{run}", every: 1h, runs-on: farm}}\n')
        assert errors == [] and s.blocks["build"].runs_on == "farm", (run, [(e.code, e.message) for e in errors])
    (model / "go.sh").write_text("exec ergostat\n")
    _, errors, _ = runs(model, '  build: {type: program, run: "../model/go.sh", every: 1h, runs-on: farm}\n')
    assert [e.code for e in errors] == ["runs-on-calls"]                        # back inside the folder: read


def test_a_pool_is_used_by_one_shard(tmp_path):
    two = ('  a: {type: program, run: "true", every: 1h, runs-on: farm, system: left}\n'
           '  b: {type: program, run: "true", every: 1h, runs-on: farm, system: right}\n')
    _, errors, lines = runs(tmp_path, two)
    assert [e.code for e in errors] == ["pool-across-shards"]
    assert "b:" in lines[errors[0].where.line - 1]                               # the second block's runs-on
    s, errors, _ = runs(tmp_path, two.replace("right", "left"))
    assert errors == [] and {b.runs_on for b in s.blocks.values()} == {"farm"}   # one system: one shard
    shared = two.replace("system: left", "system: left, agent: box").replace("system: right", "system: right, agent: box")
    _, errors, _ = runs(tmp_path, shared, rest="agents:\n  box: {kind: program}\n" + FARM)
    assert errors == [], [(e.code, e.message) for e in errors]                 # a shared agent joins the shards


def test_a_pool_cannot_be_called_local(tmp_path):
    _, errors, lines = runs(tmp_path, '  build: {type: program, run: "true", every: 1h}\n',
                            rest="compute:\n  local: {nodes: [{ssh: node-1}]}\n")
    assert [e.code for e in errors] == ["bad-name"] and "local" in lines[errors[0].where.line - 1]


def test_the_ceilings_hold_at_their_edge(tmp_path):
    s, errors, _ = read(tmp_path, f"a:\n  {nodes(64)}")
    assert errors == [] and len(s.compute["a"].nodes) == 64        # one pool at the 64-node edge, alone
    _, errors, _ = read(tmp_path, f"a:\n  {nodes(65)}")
    assert [e.code for e in errors] == ["too-many-nodes"]
    _, errors, _ = read(tmp_path, f"a:\n  {nodes(33)}\nb:\n  {nodes(32)}")
    assert [e.code for e in errors] == ["too-many-nodes"]          # 65 nodes over all pools, though each is under
    _, errors, _ = read(tmp_path, f"a:\n  {nodes(32)}\n  slots: 4\nb:\n  {nodes(32)}\n  slots: 5")
    assert [e.code for e in errors] == ["too-many-runs"]           # 64 nodes; 32·4 + 32·5 = 288 runs
    s, errors, _ = read(tmp_path, f"a:\n  {nodes(32)}\n  slots: 4\nb:\n  {nodes(32)}\n  slots: 4")
    assert errors == [] and sum(len(p.nodes) * p.slots for p in s.compute.values()) == 256
    _, errors, _ = read(tmp_path, "c:\n  nodes: [{connect: [w]}]\n  slots: 64\n  limits: {wall: 1d, log: 1GiB}")
    assert errors == []
