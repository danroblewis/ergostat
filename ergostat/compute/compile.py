"""Reading ``compute:`` (SPEC §12k, *Compute pools*) into the spec, every mistake said with where it was written, and
every number that multiplies runs held under a ceiling here (review lesson 4). Called by the spec compiler with
itself, for its ``named``, ``keys``, ``duration`` and ``err``. Nothing is run, reached or read: a secret's file is
only named."""

from __future__ import annotations

import math
import re

from ..spec.ir import NAME, ComputePool

POOL_KEYS = {"nodes", "backend", "image", "slots", "limits", "repos", "secrets", "labels", "description"}
LIMIT_KEYS = {"cpus", "memory", "pids", "disk", "wall", "network", "log"}
BACKENDS = ("process", "docker")
NETWORKS = ("none", "host")
MAX_NODES = 64                    # a pool's nodes, and all pools' together (one connection each)
MAX_SLOTS = 64                    # runs at once on one node
MAX_RUNS = 256                    # nodes × slots, summed over all pools
MAX_WALL = 86400.0                # a run's wall time: a day
LOG, MAX_LOG = 64 << 20, 1 << 30  # each of a run's output files: 64 MiB unless said, at most 1 GiB
HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,252}$")    # a Host of the owner's ~/.ssh/config (never an option)
ADDRESS = re.compile(r"^[0-9.]+$|[:\[\]]")                  # IPv4, IPv6, or a host:port
SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:([kmgt])i?)?b?\s*$", re.IGNORECASE)
SECRET = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")             # an environment variable's name
LABEL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
NODE = "{ssh: HOST} or {connect: [COMMAND, ARG, ...]}"


def size(v) -> int | None:
    """Bytes, from ``4g``, ``512MiB`` or ``1024`` (bytes); multiples of 1024. None: not a size above 0."""
    if isinstance(v, int) and not isinstance(v, bool):
        return v if v > 0 else None
    m = SIZE.match(v) if isinstance(v, str) else None
    if m is None:
        return None
    return int(float(m.group(1)) * 1024 ** " kmgt".index((m.group(2) or " ").lower())) or None


def whole(c, m, key: str, what: str, default: int, most: int, over: str) -> int:
    v = m.get(key, default)
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        c.err(f"{what}.{key}: a whole number, 1 or more", m.at(key), "bad-number")
        return default
    if v > most:
        c.err(f"{what}.{key}: at most {most}", m.at(key), over)
        return most
    return v


def nodes(c, m, what: str) -> list[dict]:
    xs = m.get("nodes")
    if not isinstance(xs, list) or not xs:
        c.err(f"{what}.nodes: a list of nodes, each {NODE}", m.at("nodes"), "missing-key" if xs is None else "bad-node")
        return []
    if len(xs) > MAX_NODES:
        c.err(f"{what}.nodes: at most {MAX_NODES} ({len(xs)} here)", m.at("nodes"), "too-many-nodes")
        return []
    out = []
    for i, x in enumerate(xs, 1):
        at, one = getattr(x, "where", None) or m.at("nodes"), f"{what}.nodes[{i}]"
        h = x.get("ssh") if isinstance(x, dict) else None
        if not isinstance(x, dict) or len(x) != 1 or not {"ssh", "connect"} & set(x):
            c.err(f"{one}: {NODE}, one of them", at, "bad-node")
        elif isinstance(h, str) and "@" in h:
            c.err(f"{one}.ssh: a Host name of your ~/.ssh/config, not a user (its User line says that)", at,
                  "node-names-user")
        elif isinstance(h, str) and ADDRESS.search(h):
            c.err(f"{one}.ssh: a Host name of your ~/.ssh/config, not an address (its HostName line says that)", at,
                  "node-names-address")
        elif "ssh" in x:
            if isinstance(h, str) and HOST.match(h):
                out.append({"ssh": h})
            else:
                c.err(f"{one}.ssh: a Host name of your ~/.ssh/config (letters, digits, . _ -)", at, "bad-node")
        elif isinstance(x["connect"], list) and x["connect"] and all(isinstance(a, str) and a for a in x["connect"]):
            out.append({"connect": list(x["connect"])})
        else:
            c.err(f"{one}.connect: the command and its arguments, as a list of words", at, "bad-node")
    return out


def limits(c, m, what: str, backend: str) -> dict:
    lim, out = m.get("limits"), {"log": LOG}
    if lim is None:
        return out
    if not isinstance(lim, dict):
        c.err(f"{what}.limits: a map of {', '.join(sorted(LIMIT_KEYS))}", m.at("limits"), "not-a-map")
        return out
    what = f"{what}.limits"
    c.keys(lim, LIMIT_KEYS, what)
    for k in ("memory", "disk", "log"):
        n = size(lim[k]) if k in lim else None
        if k in lim and n is None:
            c.err(f"{what}.{k}: a size above 0, like 512m, 4g or 1GiB (or a number of bytes)", lim.at(k), "bad-size")
        elif k == "log" and n is not None and n > MAX_LOG:
            c.err(f"{what}.log: at most 1g (each of a run's output files)", lim.at(k), "log-over-cap")
        elif n is not None:
            out[k] = n
    wall = c.duration(lim, "wall", what)
    if wall is not None and not wall <= MAX_WALL:                     # NaN refused too
        c.err(f"{what}.wall: at most a day (1d)", lim.at("wall"), "wall-over-a-day")
    elif wall is not None:
        out["wall"] = wall
    cpus = lim.get("cpus")
    if cpus is not None and (isinstance(cpus, bool) or not isinstance(cpus, int | float) or not math.isfinite(cpus)
                             or cpus <= 0):
        c.err(f"{what}.cpus: a number above 0 (2, or 0.5 for half of one)", lim.at("cpus"), "bad-number")
    elif cpus is not None:
        out["cpus"] = float(cpus)
    if "pids" in lim:
        out["pids"] = whole(c, lim, "pids", what, 1, 1 << 22, "bad-number")
    net = lim.get("network")
    if net is not None and net not in NETWORKS:
        c.err(f"{what}.network: {' or '.join(NETWORKS)}", lim.at("network"), "bad-network")
    elif net == "none" and backend == "process":
        c.err(f"{what}.network: none needs backend: docker (the process backend cannot hold a run off the network, "
              f"and does not pretend to)", lim.at("network"), "network-on-process")
    elif net is not None:
        out["network"] = net
    return out


def table(c, m, key: str, what: str, names: re.Pattern, say: str) -> dict[str, str]:
    v = m.get(key)
    if v is None:
        return {}
    if not isinstance(v, dict) or not all(isinstance(k, str) and names.match(k) and isinstance(x, str) and x
                                          for k, x in v.items()):
        c.err(f"{what}.{key}: {say}", m.at(key), f"bad-{key}")
        return {}
    return dict(v)


def compute(c, spec) -> None:
    for name, m, what in c.named("compute"):
        c.keys(m, POOL_KEYS, what)
        backend = str(m.get("backend") or "process")
        if backend not in BACKENDS:
            c.err(f"{what}.backend: {' or '.join(BACKENDS)}", m.at("backend"), "bad-backend")
        image = m.get("image")
        if image is not None and (not isinstance(image, str) or not image):
            c.err(f"{what}.image: the image's name, like ergostat-run:1", m.at("image"), "bad-image")
            image = None
        elif backend == "docker" and image is None:
            c.err(f"{what}: backend: docker needs image: (what each run's container is made from)", m.where,
                  "docker-needs-image")
        spec.compute[name] = ComputePool(
            name, nodes(c, m, what), backend, image, whole(c, m, "slots", what, 1, MAX_SLOTS, "too-many-slots"),
            limits(c, m, what, backend),
            table(c, m, "repos", what, NAME, "a map of a name to the repository's path here"),
            table(c, m, "secrets", what, SECRET, "a map of an environment variable's name (API_TOKEN) to the file "
                                                 "it is read from"),
            table(c, m, "labels", what, LABEL, "a map of a label to the text a node must say for it"),
            c.text(m, "description"), m.where)
    pools = list(spec.compute.values())
    if pools and sum(len(p.nodes) for p in pools) > MAX_NODES:
        c.err(f"compute: at most {MAX_NODES} nodes over all pools ({sum(len(p.nodes) for p in pools)} here)",
              pools[-1].where, "too-many-nodes")
    if pools and sum(len(p.nodes) * p.slots for p in pools) > MAX_RUNS:
        c.err(f"compute: nodes × slots at most {MAX_RUNS} over all pools "
              f"({sum(len(p.nodes) * p.slots for p in pools)} here)", pools[-1].where, "too-many-runs")
