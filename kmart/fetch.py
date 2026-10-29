"""Kmart transport: plain curl_cffi with browser-impersonated TLS. No
browser, no cookies, no tokens. Egress: a sticky AU residential exit per
session (config.kmart_proxy(), knob KMART_EXIT = "au") — every surface below
answered 200 on 2/2 AU residential ports from pod
scrapers-patchright-depl-fdd5b584c-pq7mg on 2026-10-28 (tools/egress_probe.py
table in config.py). A retryable failure drops the thread's session, so a
retry rides a fresh exit.

Upstream surfaces (all open, probed 2026-10-28):

  * CONSTRUCTOR  https://ac.cnstrc.com — Kmart's catalogue engine
    (Constructor.io, public index key config.KMART_CONSTRUCTOR_KEY read
    from the site's __NEXT_DATA__ `constructorApiKey`). search/<term>,
    browse/group_id|collection_id|Brand|Shops/<value>, browse/items?ids=,
    browse/groups (the category tree), autocomplete/<term> and
    recommendations/v1/pods/bestsellers_products. Every call takes
    fmt_options[show_hidden_fields]=true (the PDP description HTML and
    SavePrice) and fmt_options[show_hidden_facets]=true (per-state
    availability, clearance, onlineOnly). Hard limits (400 otherwise):
    200 results per page, 100 ids per items call, 100 recommendations.
    Unknown ids / groups / brands / shops answer 200 with zero results;
    an unknown collection answers a real 404.

  * YOTPO  https://api-cdn.yotpo.com/v1/widget/<app key>/products/<keycode>/
    reviews.json — the review widget's public JSON (app key from the site
    bundle), 150 reviews per page max, sort / star filters. Marketplace
    (S-prefixed) items carry no Yotpo reviews.

  * KMART PAGES  https://www.kmart.com.au/store-detail/<slug>/ and
    /shop/<slug>/ — server-rendered Next.js pages whose __NEXT_DATA__
    carries the store / shop record. Unknown slugs answer a real 404.
    (Product and search pages are Kasada-challenged and never fetched:
    Constructor carries every field the PDP renders.)

  * SITEMAPS  /sitemap.xml and /sitemap/au/*-sitemap.xml.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  KmartUpstreamError  transport failure / 5xx / non-JSON       — retryable
  KmartBlocked        403 / 429 / challenge page               — retryable
  KmartBadRequest     upstream 400 (Constructor validation)    — never retried
  KmartNotFound       404 / unknown id                         — never retried
"""
import os
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from kmart.refs import SITE, SITEMAP_INDEX

IMPERSONATE = "chrome"
JSON_TIMEOUT = 30
PAGE_TIMEOUT = 45       # store / shop pages are 1.7-3.6 MB
SITEMAP_TIMEOUT = 60    # product sitemaps are ~6 MB

CONSTRUCTOR = "https://ac.cnstrc.com"
CONSTRUCTOR_CLIENT = "ciojs-client-2.62.2"   # the version the site bundle sends (2026-10-28)
YOTPO = "https://api-cdn.yotpo.com/v1/widget"

MAX_PAGE_SIZE = 200       # Constructor: num_results_per_page <= 200
MAX_ITEM_IDS = 100        # Constructor: ids must contain at most 100 elements
MAX_RECOMMENDATIONS = 100  # Constructor: num_results <= 100
MAX_REVIEWS_PER_PAGE = 150  # Yotpo widget cap

JSON_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-AU,en;q=0.9",
    "origin": SITE,
    "referer": SITE + "/",
}
PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "accept-language": "en-AU,en;q=0.9",
    "upgrade-insecure-requests": "1",
}


class KmartUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected payload — retryable."""


class KmartBlocked(KmartUpstreamError, Blocked):
    """403 / 429 or a challenge page where JSON / HTML was expected — retryable."""


class KmartBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class KmartNotFound(NotFound):
    """Product / category / seller / store does not exist — never retried."""


# One session per cheroot worker thread (a curl handle must not be shared
# across threads); these GETs are stateless, so thread-lifetime sessions
# with keep-alive are enough.
_local = threading.local()


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = config.kmart_proxy()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        _local.session = sess
        _local.client_id = str(uuid.uuid4())   # Constructor's per-browser `i`
    return sess


def _drop_session():
    """Close the thread's session so a poisoned keep-alive connection dies."""
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _retrying(fn):
    """Run fn() under the shared retry policy (KmartUpstreamError only;
    NotFound / BadRequest surface immediately)."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except KmartUpstreamError as e:
            last = e
            _drop_session()
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def _classify(resp, label):
    if resp.status_code == 404:
        raise KmartNotFound(f"{label} not found")
    if resp.status_code == 400:
        raise KmartBadRequest(resp.text[:200])
    if resp.status_code in (401, 403, 429):
        raise KmartBlocked(f"HTTP {resp.status_code} for {label}")
    if resp.status_code != 200:
        raise KmartUpstreamError(f"HTTP {resp.status_code} for {label}")


def _get(url, params, headers, timeout, label):
    try:
        return _session().get(url, params=params, headers=headers, timeout=timeout)
    except Exception as e:
        raise KmartUpstreamError(f"request failed for {label}: {type(e).__name__}: {e}")


def _json(resp, label):
    try:
        return resp.json()
    except Exception:
        raise KmartBlocked(f"non-JSON response for {label}: {resp.text[:120]}")


# ---- Constructor.io -------------------------------------------------------------

def _constructor_params(extra=None, hidden=True):
    _session()
    params = [("key", config.KMART_CONSTRUCTOR_KEY), ("c", CONSTRUCTOR_CLIENT),
              ("i", _local.client_id), ("s", "1")]
    if hidden:
        params += [("fmt_options[show_hidden_fields]", "true"),
                   ("fmt_options[show_hidden_facets]", "true")]
    for key, value in (extra or []):
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            params += [(key, v) for v in value]
        else:
            params.append((key, value))
    return params


def constructor_get(path, extra=None, label=None, hidden=True, timeout=JSON_TIMEOUT):
    """GET one Constructor.io route -> the JSON payload. 400s carry
    Constructor's own message (an unknown facet / bad filter)."""
    label = label or path

    def once():
        resp = _get(CONSTRUCTOR + path, _constructor_params(extra, hidden), JSON_HEADERS,
                    timeout, label)
        if resp.status_code == 404:
            # collections are the one browse surface with a real 404
            payload = _json(resp, label) if resp.text.startswith("{") else {}
            raise KmartNotFound(payload.get("message") or f"{label} not found")
        if resp.status_code == 400:
            payload = _json(resp, label) if resp.text.startswith("{") else {}
            raise KmartBadRequest(payload.get("message") or resp.text[:200])
        _classify(resp, label)
        payload = _json(resp, label)
        if not isinstance(payload, dict) or "response" not in payload and "sections" not in payload:
            raise KmartUpstreamError(f"unexpected payload shape for {label}: {resp.text[:120]}")
        return payload
    return _retrying(once)


def _listing_params(page, per_page, filters=None, sort=None):
    extra = [("page", page), ("num_results_per_page", min(per_page, MAX_PAGE_SIZE))]
    for name, values in (filters or {}).items():
        if values is None:
            continue
        extra.append((f"filters[{name}]", values))
    if sort:
        extra += [("sort_by", sort[0]), ("sort_order", sort[1])]
    return extra


def fetch_search(term, page=1, per_page=40, filters=None, sort=None):
    """search/<term>: one results page with facets, groups and sort options."""
    from urllib.parse import quote
    return constructor_get(f"/search/{quote(term, safe='')}",
                           _listing_params(page, per_page, filters, sort), f"search {term!r}")


def fetch_browse(kind, value, page=1, per_page=40, filters=None, sort=None):
    """browse/<kind>/<value>: kind is group_id, collection_id, Brand or
    Shops (a facet name); value is the group id, collection slug or facet
    value. Unknown values answer zero results (collections: a 404)."""
    from urllib.parse import quote
    return constructor_get(f"/browse/{kind}/{quote(str(value), safe='')}",
                           _listing_params(page, per_page, filters, sort), f"{kind} {value!r}")


def fetch_items(item_ids):
    """browse/items?ids=P_..: up to 100 items by Constructor id; unknown ids
    are simply absent from the results."""
    ids = list(item_ids)[:MAX_ITEM_IDS]
    return constructor_get("/browse/items", [("ids", ids), ("num_results_per_page", MAX_PAGE_SIZE)],
                           f"items {','.join(ids[:3])}")


def fetch_groups():
    """browse/groups with the full depth: the whole category tree (~2.3 MB,
    3,352 groups on 2026-10-28)."""
    return constructor_get("/browse/groups", [("fmt_options[groups_max_depth]", 10)],
                           "category tree", hidden=False, timeout=SITEMAP_TIMEOUT)


def fetch_autocomplete(term, products=8, suggestions=10):
    from urllib.parse import quote
    return constructor_get(f"/autocomplete/{quote(term, safe='')}",
                           [("num_results_Products", products),
                            ("num_results_Search Suggestions", suggestions)],
                           f"autocomplete {term!r}", hidden=False)


def fetch_recommendations(pod, num_results=20, filters=None):
    extra = [("num_results", min(num_results, MAX_RECOMMENDATIONS))]
    for name, values in (filters or {}).items():
        if values is not None:
            extra.append((f"filters[{name}]", values))
    return constructor_get(f"/recommendations/v1/pods/{pod}", extra, f"recommendations {pod}")


# ---- Yotpo reviews ----------------------------------------------------------------

def fetch_reviews(keycode, page=1, per_page=10, sort=None, star=None):
    """The Yotpo review widget JSON for one keycode. `sort` is a (field,
    direction) pair from the site's own options (date / votes_up / rating /
    images). An unknown keycode answers 200 with no product and no reviews."""
    params = [("per_page", min(per_page, MAX_REVIEWS_PER_PAGE)), ("page", page)]
    if sort:
        params += [("sort", sort[0]), ("direction", sort[1])]
    if star:
        params.append(("star", star))
    label = f"reviews {keycode}"

    def once():
        resp = _get(f"{YOTPO}/{config.KMART_YOTPO_KEY}/products/{keycode}/reviews.json",
                    params, JSON_HEADERS, JSON_TIMEOUT, label)
        _classify(resp, label)
        payload = _json(resp, label)
        if not isinstance(payload, dict) or not isinstance(payload.get("response"), dict):
            raise KmartUpstreamError(f"unexpected Yotpo payload for {label}: {resp.text[:120]}")
        return payload
    return _retrying(once)


# ---- kmart.com.au pages -------------------------------------------------------------

def _page(path, label, timeout=PAGE_TIMEOUT, headers=PAGE_HEADERS):
    def once():
        resp = _get(SITE + path, None, headers, timeout, label)
        _classify(resp, label)
        text = resp.text
        if "__NEXT_DATA__" not in text and "<urlset" not in text and "<sitemapindex" not in text:
            # Kasada's challenge shell is a tiny page with no Next.js payload
            raise KmartBlocked(f"challenge page for {label}")
        return text
    return _retrying(once)


def fetch_store_page(slug):
    """GET /store-detail/<slug>/ -> HTML (404 for an unknown slug)."""
    return _page(f"/store-detail/{slug}/", f"store {slug}")


def fetch_shop_page(slug):
    """GET /shop/<slug>/ -> HTML (404 for an unknown slug)."""
    return _page(f"/shop/{slug}/", f"seller {slug}")


def fetch_sitemap(path=None):
    """GET one sitemap (the index when path is None) -> XML text."""
    if path is None:
        return _page(SITEMAP_INDEX[len(SITE):], "sitemap index", SITEMAP_TIMEOUT)
    return _page(path, f"sitemap {path}", SITEMAP_TIMEOUT)
