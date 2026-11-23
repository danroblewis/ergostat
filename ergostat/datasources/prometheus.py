"""A Prometheus-compatible source: PromQL, asked as a range query (``GET /api/v1/query_range``) by the server, so the
browser never holds the source's address or credentials. A GET to that one path is the only request it makes, and it is
ended at the query's time bound however slowly the source answers."""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
import urllib.parse

from . import SourceError

TYPE = "prometheus"
KEYS = {"url"}
LANGUAGE = "PromQL"
_PATH = "/api/v1/query_range"
_MOST_BYTES = 8 * 1024 * 1024     # of one answer


def _said(body: bytes) -> str:
    """What Prometheus said was wrong, from its error answer."""
    try:
        got = json.loads(body)
        return f"{got.get('errorType', 'error')}: {got.get('error', 'failed')}"[:300]
    except (ValueError, AttributeError, RecursionError):
        return "it did not say why"


def _connect(deadline: float, held: list):
    """``socket.create_connection``, each address tried with only the time left, so connecting ends by the deadline;
    the socket is kept in ``held`` (the response takes it over from the connection, and the cut must still reach it)."""
    def connect(addr, timeout=None, source_address=None):
        err: OSError = OSError("no address")
        for *_, sa in socket.getaddrinfo(addr[0], addr[1], 0, socket.SOCK_STREAM):
            left = deadline - time.monotonic()
            if left <= 0:
                break
            try:
                held.append(socket.create_connection(sa[:2], left, source_address))
                return held[-1]
            except OSError as e:
                err = e
        raise err
    return connect


def _cut(held: list, late: threading.Event) -> None:
    """At the deadline: end the connection, so a source that stalls or trickles stops holding the request."""
    late.set()
    for s in held:
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def _get(src, params: dict, seconds: float) -> dict:
    """One GET, ended ``seconds`` from now however the source answers (connecting, a stalled header, a trickled body).
    Only name resolution is left to the system's resolver, which this cannot interrupt."""
    u = urllib.parse.urlsplit(src.url.rstrip("/"))
    if u.scheme not in ("http", "https") or not u.hostname:
        raise SourceError("unreachable", f"source {src.name!r} has no http or https url")
    deadline = time.monotonic() + seconds
    try:
        conn = (http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection)(
            u.hostname, u.port, timeout=seconds)
    except ValueError as e:                         # (a port that is not a number)
        raise SourceError("unreachable", f"could not reach source {src.name!r} ({type(e).__name__})") from e
    held: list = []
    conn._create_connection = _connect(deadline, held)
    late = threading.Event()
    cut = threading.Timer(seconds, _cut, (held, late))
    cut.daemon = True
    cut.start()
    try:
        conn.request("GET", f"{u.path}{_PATH}?{urllib.parse.urlencode(params)}", headers={"Accept": "application/json"})
        r = conn.getresponse()
        body = r.read(_MOST_BYTES + 1)
    except (OSError, ValueError, http.client.HTTPException) as e:   # (never the address: it may hold credentials)
        if late.is_set() or time.monotonic() >= deadline:
            raise SourceError("limit", f"source {src.name!r} did not answer within {seconds:g} s") from e
        raise SourceError("unreachable", f"could not reach source {src.name!r} ({type(e).__name__})") from e
    finally:
        cut.cancel()
        conn.close()
        for s in held:
            s.close()
    if late.is_set():                               # (cut short: what was read is not the whole answer)
        raise SourceError("limit", f"source {src.name!r} did not answer within {seconds:g} s")
    if r.status in (400, 422):
        raise SourceError("refused", f"source {src.name!r} refused the query ({_said(body[:_MOST_BYTES])})")
    if r.status != 200:
        raise SourceError("unreachable", f"source {src.name!r} answered {r.status}")
    if len(body) > _MOST_BYTES:
        raise SourceError("limit", f"source {src.name!r} answered more than {_MOST_BYTES // 2**20} MB; narrow the query")
    try:
        got = json.loads(body)
    except (ValueError, RecursionError) as e:
        raise SourceError("unreachable", f"source {src.name!r} did not answer in JSON") from e
    if not isinstance(got, dict) or got.get("status") != "success":
        raise SourceError("refused", f"source {src.name!r} refused the query ({_said(body)})")
    return got.get("data") or {}


def _name(metric: dict, text: str) -> str:
    labels = ", ".join(f'{k}="{v}"' for k, v in sorted(metric.items()) if k != "__name__")
    base = metric.get("__name__", "")
    return f"{base}{{{labels}}}" if labels else base or text.strip()[:60]


def _number(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError, OverflowError):
        return None


def query(src, text: str, w) -> list:
    data = _get(src, {"query": text, "start": f"{w.start:.3f}", "end": f"{w.end:.3f}", "step": f"{w.step:g}",
                      "timeout": f"{w.seconds:g}s"}, w.seconds)
    if data.get("resultType") != "matrix" or not isinstance(data.get("result"), list):
        raise SourceError("refused", f"source {src.name!r} answered {data.get('resultType')!r}, not a range of series")
    out = []
    for s in data["result"]:
        pts = s.get("values") if isinstance(s, dict) else None
        if not isinstance(pts, list):
            raise SourceError("refused", f"source {src.name!r} answered a series with no values")
        out.append((_name(s.get("metric") or {}, text),
                    [(t, _number(v)) for p in pts if isinstance(p, list) and len(p) == 2
                     for t, v in [p] if isinstance(t, int | float)]))
    return out
