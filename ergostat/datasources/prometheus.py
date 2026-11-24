"""A Prometheus-compatible source: PromQL, asked as a range query (``GET /api/v1/query_range``) by the server, so the
browser never holds the source's address or credentials; its metadata (``/api/v1/labels``, ``/api/v1/label/<name>/values``)
gives the names an editor completes, and ``/api/v1/label/<name>/values`` also a dashboard variable's values. GETs of
those paths are the only requests it makes, each ended at its time bound however slowly the source answers."""

from __future__ import annotations

import http.client
import json
import re
import socket
import threading
import time
import urllib.parse

from . import SourceError

TYPE = "prometheus"
KEYS = {"url"}
LANGUAGE = "PromQL"
_PATH = "/api/v1/query_range"
_LABELS = "/api/v1/label/{}/values"     # a dashboard variable's label_values
_MOST_BYTES = 8 * 1024 * 1024     # of one answer
_MOST_NAME_BYTES = 256 * 1024     # of one metadata answer: past it, only the names read before it are kept
_LINE_COL = re.compile(r"\b(\d+):(\d+): parse error")
_AT_CHAR = re.compile(r"parse error at (?:line \d+, )?char (\d+)")


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


def _tls(conn, host: str, held: list, late: threading.Event):
    """``HTTPSConnection.connect``, with the TLS socket kept in ``held`` before its handshake: wrapping takes the plain
    socket's file over (it is left with none), so a cut that reached only the plain socket would end nothing."""
    def connect():
        http.client.HTTPConnection.connect(conn)
        conn.sock = s = conn._context.wrap_socket(conn.sock, server_hostname=host, do_handshake_on_connect=False)
        held.append(s)
        if late.is_set():                           # (cut between the wrap and the hold: the cut missed this socket)
            raise TimeoutError("past the deadline")
        s.do_handshake()
    return connect


def _cut(held: list, late: threading.Event) -> None:
    """At the deadline: end the connection, so a source that stalls or trickles stops holding the request."""
    late.set()
    for s in held:
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def _ask(src, path: str, params: dict | list, seconds: float, most: int) -> tuple[int, bytes]:
    """One GET of ``path``, ended ``seconds`` from now however the source answers (connecting, a stalled header, a
    trickled body), and its status and at most ``most + 1`` bytes of its body. Only name resolution is left to the
    system's resolver, which this cannot interrupt."""
    u = urllib.parse.urlsplit(src.url.rstrip("/"))
    if u.scheme not in ("http", "https") or not u.hostname:
        raise SourceError("unreachable", f"source {src.name!r} has no http or https url")
    deadline = time.monotonic() + seconds
    try:
        conn = (http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection)(
            u.hostname, u.port, timeout=seconds)
    except ValueError as e:                         # (a port that is not a number)
        raise SourceError("unreachable", f"could not reach source {src.name!r} ({type(e).__name__})") from e
    if extra := getattr(src, "options", {}).get("extra_label"):   # (the built-in source: VictoriaMetrics holds it to one project)
        params = [*(params.items() if isinstance(params, dict) else params), ("extra_label", extra)]
    held: list = []
    conn._create_connection = _connect(deadline, held)
    late = threading.Event()
    if u.scheme == "https":
        conn.connect = _tls(conn, u.hostname, held, late)
    cut = threading.Timer(seconds, _cut, (held, late))
    cut.daemon = True
    cut.start()
    try:
        conn.request("GET", f"{u.path}{path}?{urllib.parse.urlencode(params)}", headers={"Accept": "application/json"})
        r = conn.getresponse()
        body = r.read(most + 1)
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
        said = _said(body[:most])
        raise SourceError("refused", f"source {src.name!r} refused the query ({said})", _at(said))
    return r.status, body


def _at(said: str) -> tuple[int, int] | None:
    """Where Prometheus said the text is wrong: ``1:5: parse error: ...`` (line and column), or ``at char 5``;
    the column counts the text's UTF-8 bytes, as Prometheus does, and the page turns it into a place in its text."""
    m = _LINE_COL.search(said)
    if m:
        return int(m[1]), int(m[2])
    m = _AT_CHAR.search(said)
    return (1, int(m[1])) if m else None


def _get(src, params: dict, seconds: float, path: str = _PATH) -> dict:
    status, body = _ask(src, path, params, seconds, _MOST_BYTES)
    if status != 200:
        raise SourceError("unreachable", f"source {src.name!r} answered {status}")
    if len(body) > _MOST_BYTES:
        raise SourceError("limit", f"source {src.name!r} answered more than {_MOST_BYTES // 2**20} MB; narrow the query")
    try:
        got = json.loads(body)
    except (ValueError, RecursionError) as e:
        raise SourceError("unreachable", f"source {src.name!r} did not answer in JSON") from e
    if not isinstance(got, dict) or got.get("status") != "success":
        raise SourceError("refused", f"source {src.name!r} refused the query ({_said(body)})")
    return got.get("data")


def _name(metric: dict, text: str) -> str:
    labels = ", ".join(f'{k}="{v}"' for k, v in sorted(metric.items()) if k != "__name__")
    base = metric.get("__name__", "")
    return f"{base}{{{labels}}}" if labels else base or text.strip()[:60]


def _number(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError, OverflowError):
        return None


def values(src, selector: str | None, label: str, w) -> list:
    """The values ``label`` takes over the window, among the series ``selector`` picks (all, when None)."""
    params = {"start": f"{w.since:.3f}", "end": f"{w.until:.3f}", **({"match[]": selector} if selector else {})}
    data = _get(src, params, w.seconds, _LABELS.format(urllib.parse.quote(label, safe="")))
    if not isinstance(data, list):
        raise SourceError("refused", f"source {src.name!r} answered with no list of values")
    return data


def query(src, text: str, w) -> list:
    data = _get(src, {"query": text, "start": f"{w.start:.3f}", "end": f"{w.end:.3f}", "step": f"{w.step:g}",
                      "timeout": f"{w.seconds:g}s"}, w.seconds)
    if not isinstance(data, dict):
        data = {}
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


_NAMES_START = re.compile(rb'\s*\{\s*"status"\s*:\s*"success"\s*,\s*"data"\s*:\s*\[')
_RE_SPECIAL = re.compile(r"([\\.+*?()|\[\]{}^$])")


def _starting(prefix: str) -> str:
    """A PromQL string matching what starts with ``prefix`` (RE2, which anchors it; its special characters escaped)."""
    return json.dumps(_RE_SPECIAL.sub(r"\\\1", prefix) + ".*")


def _names(src, body: bytes, prefix: str, most: int) -> tuple[list, bool]:
    """The first ``most`` names starting with ``prefix`` in a ``{"status": "success", "data": [...]}`` answer, read one
    by one: an answer cut at the byte bound still gives the names before the cut, and is said to have ``more``."""
    m = _NAMES_START.match(body)
    if not m:
        raise SourceError("refused", f"source {src.name!r} did not answer with names ({_said(body[:_MOST_NAME_BYTES])})")
    text, dec, out, i = body[m.end():_MOST_NAME_BYTES].decode("utf-8", "ignore"), json.JSONDecoder(), [], 0
    while True:
        while i < len(text) and text[i] in " \t\r\n,":
            i += 1
        if i < len(text) and text[i] == "]":
            return out, False
        if len(out) >= most:
            return out, True
        try:
            v, i = dec.raw_decode(text, i)
        except (ValueError, RecursionError):        # (cut at the byte bound, or not a list of names)
            return out, True
        if isinstance(v, str) and v.startswith(prefix):
            out.append(v)


def suggest(src, what: str, prefix: str, metric: str, label: str, seconds: float, most: int) -> tuple[list, bool]:
    """Metric names, label names or one label's values, from Prometheus's metadata API (``GET``s of ``/api/v1/labels``
    and ``/api/v1/label/<name>/values``), narrowed by the source to ``prefix`` and ``metric`` and asked for at most
    ``most + 1`` (``limit``, Prometheus 2.49 and later); a source that sends more is read only to the byte bound."""
    if what == "metrics":
        path, sel = "/api/v1/label/__name__/values", f"{{__name__=~{_starting(prefix)}}}" if prefix else ""
    elif what == "labels":
        path, sel = "/api/v1/labels", metric
    else:
        path, sel = f"/api/v1/label/{label}/values", metric + (f"{{{label}=~{_starting(prefix)}}}" if prefix else "")
    params = [("limit", str(most + 1))] + ([("match[]", sel)] if sel else [])
    status, body = _ask(src, path, params, seconds, _MOST_NAME_BYTES)
    if status != 200:
        raise SourceError("unreachable", f"source {src.name!r} answered {status}")
    return _names(src, body, prefix, most)
