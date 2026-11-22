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


def test_the_ceilings_hold_at_their_edge(tmp_path):
    _, errors, _ = read(tmp_path, f"a:\n  {nodes(33)}\nb:\n  {nodes(32)}")
    assert [e.code for e in errors] == ["too-many-nodes"]          # 65 nodes over all pools, though each is under
    _, errors, _ = read(tmp_path, f"a:\n  {nodes(32)}\n  slots: 4\nb:\n  {nodes(32)}\n  slots: 5")
    assert [e.code for e in errors] == ["too-many-runs"]           # 64 nodes; 32·4 + 32·5 = 288 runs
    s, errors, _ = read(tmp_path, f"a:\n  {nodes(32)}\n  slots: 4\nb:\n  {nodes(32)}\n  slots: 4")
    assert errors == [] and sum(len(p.nodes) * p.slots for p in s.compute.values()) == 256
    _, errors, _ = read(tmp_path, "c:\n  nodes: [{connect: [w]}]\n  slots: 64\n  limits: {wall: 1d, log: 1GiB}")
    assert errors == []
