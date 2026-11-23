"""A Prometheus-compatible source: PromQL, asked as a range query (``GET /api/v1/query_range``) by the server, so the
browser never holds the source's address or credentials. A GET to that one path is the only request it makes."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

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


def _get(src, params: dict, seconds: float) -> dict:
    url = f"{src.url.rstrip('/')}{_PATH}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=seconds) as r:  # noqa: S310 (the model's own source)
            body = r.read(_MOST_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code in (400, 422):
            raise SourceError("refused", f"source {src.name!r} refused the query ({_said(e.read(_MOST_BYTES))})") from e
        raise SourceError("unreachable", f"source {src.name!r} answered {e.code}") from e
    except (OSError, ValueError) as e:              # (never the address: it may hold credentials)
        raise SourceError("unreachable", f"could not reach source {src.name!r} ({type(e).__name__})") from e
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
