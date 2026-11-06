"""Parsel-Bina GIS: kucuk JSON HTTP istemcisi (yalniz stdlib).

Adi bilerek `http.py` DEGILDIR: script klasoru `sys.path`'in basinda oldugu
icin `http.py` standart kutuphanenin `http` paketini golgeler ve `urllib`
bozulur.

Testler `set_transport` ile ag yerine sahte bir fonksiyon takar.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 45
QUERY_TIMEOUT = 10
USER_AGENT = "pyKalfa"


class UpstreamError(Exception):
    """Servis cevap vermedi, gecersiz cevap verdi veya hata dondurdu."""


def _urllib_transport(url, params, post, timeout):
    data = urllib.parse.urlencode(params).encode("utf-8")
    if post:
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    else:
        req = urllib.request.Request(url + "?" + data.decode("ascii"))
    req.add_header("User-Agent", USER_AGENT)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


_transport = _urllib_transport


def set_transport(fn):
    """`fn(url, params, post, timeout) -> dict`; `None` gercek aga doner."""
    global _transport
    _transport = fn or _urllib_transport


def get_json(url, params, post=False, timeout=TIMEOUT, retries=2):
    params = dict(params)
    params.setdefault("f", "json")
    host = urllib.parse.urlparse(url).netloc or url
    last = None
    for attempt in range(retries + 1):
        try:
            res = _transport(url, params, post, timeout)
        except UpstreamError:
            raise
        except (urllib.error.URLError, OSError, ValueError) as ex:
            last = ex
            if attempt < retries and _transport is _urllib_transport:
                time.sleep(0.5 * (attempt + 1))
            continue
        if not isinstance(res, dict):
            raise UpstreamError("{} gecersiz cevap dondurdu".format(host))
        if "error" in res:
            err = res["error"]
            msg = err.get("message") if isinstance(err, dict) else err
            raise UpstreamError("{} hata dondurdu: {}".format(host, msg))
        return res
    raise UpstreamError("{} yanit vermedi: {}".format(host, last))
