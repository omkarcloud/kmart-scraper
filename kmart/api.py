"""The /kmart/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs).

Three shared indexes are each ONE cached upstream build that several
endpoints slice (tofler-style, cache.cached_call inside this module):

  _tree()     the whole Constructor category tree (browse/groups, 2.3 MB):
              categories, every category / collection link resolution, the
              category block on a product, bestsellers / search filters
  _sellers()  the "Shops" facet joined with the seller sitemap: sellers,
              seller name lookups for sellers/products and the `seller`
              listing filter
  _stores()   every /store-detail/ page from the store sitemap (309 pages,
              fetched 12 at a time): stores/search and numeric store ids

Each is also memoised in-process for a short while so a burst of calls
does not pull the 2 MB tree out of PostgreSQL per request.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from cache import cached_call
from kmart import cache_config as ttl
from kmart import parsers
from kmart.fetch import (KmartBadRequest, KmartNotFound, fetch_autocomplete, fetch_browse, fetch_groups,
                         fetch_items, fetch_recommendations, fetch_reviews, fetch_search,
                         fetch_shop_page, fetch_sitemap, fetch_store_page)
from kmart.parsers import RESULT_WINDOW, SORTS
from kmart.refs import SITE, constructor_item_id, seller_link, sitemap_path
from kmart.schemas import REVIEW_SORTS

BESTSELLERS_POD = "bestsellers_products"
STORE_FETCH_WORKERS = 12
MEMO_SECONDS = 15 * 60

_memo_lock = threading.Lock()
_memo = {}


def _memoised(name, build):
    """build() at most once per MEMO_SECONDS per process (the response cache
    still holds the row for its own TTL; this only spares the DB round trip)."""
    with _memo_lock:
        hit = _memo.get(name)
        if hit and hit[0] > time.monotonic():
            return hit[1]
    value = build()
    with _memo_lock:
        _memo[name] = (time.monotonic() + MEMO_SECONDS, value)
    return value


# ---- the category tree ------------------------------------------------------------------

def _tree_record():
    root = parsers.parse_tree(fetch_groups())
    if not root:
        raise KmartNotFound("category tree is empty")
    return root


def _tree():
    return _memoised("tree", lambda: cached_call("kmart.tree", {}, _tree_record, ttl.TREE_CACHE))


def _tree_index():
    return _memoised("tree_index", lambda: parsers.index_tree(_tree()))


def _resolve_category(category):
    """A CategoryRefField value -> ("group", id) | ("collection", slug) | None."""
    if category is None:
        return None
    if category.startswith("collection:"):
        return "collection", category[len("collection:"):]
    by_id, by_path = _tree_index()
    if category.startswith("url:"):
        path = category[len("url:"):].lower()
        gid = by_path.get(path) or by_path.get(path.replace("/category/", "/", 1))
        if not gid:
            raise KmartNotFound(f"no category at {SITE}{path}")
        return "group", gid
    if category == "all" or category in by_id:
        return "group", category
    raise KmartNotFound(f"category {category} not found")


def _category_ref(group_id):
    """{id, name, link, path} for a group id, from the cached tree."""
    if not group_id:
        return None
    by_id, _ = _tree_index()
    node = by_id.get(group_id)
    if not node:
        return {"id": group_id, "name": None, "link": None, "path": None}
    return parsers.parse_group(node, with_children=False)


# ---- the seller index ------------------------------------------------------------------

def _all_facets_record():
    """browse/group_id/all with one result: every facet of the whole index."""
    return fetch_browse("group_id", "all", page=1, per_page=1)


def _all_facets():
    return _memoised("facets_all", lambda: cached_call("kmart.facets_all", {}, _all_facets_record, ttl.BRANDS_CACHE))


def _sellers_record():
    rows = parsers.parse_sitemap_urls(fetch_sitemap(sitemap_path("sellers")))
    return parsers.parse_seller_index(_all_facets(), rows)


def _sellers():
    return _memoised("sellers", lambda: cached_call("kmart.sellers_index", {}, _sellers_record, ttl.SELLERS_CACHE))


def _seller_name(slug):
    """The "Shops" facet value for a slug (what browse/Shops/<value> takes);
    a seller with a shop page but no facet row is named from the page."""
    for row in _sellers():
        if row["slug"] == slug:
            if row["name"]:
                return row["name"]
            break
    record = _seller_record(slug)   # raises KmartNotFound for an unknown slug
    return record["name"]


# ---- the store index -------------------------------------------------------------------

def _store_record(store):
    record = parsers.parse_store_page(fetch_store_page(store), store)
    if not record:
        raise KmartNotFound(f"store {store} not found")
    return record


def _store(slug):
    return cached_call("kmart.store", {"store": slug}, _store_record, ttl.STORE_CACHE)


def _stores_record():
    slugs = [row["slug"] for row in parsers.parse_sitemap_urls(fetch_sitemap(sitemap_path("stores"))) if row.get("slug")]

    def one(slug):
        try:
            return _store(slug)
        except KmartNotFound:
            return None
    with ThreadPoolExecutor(max_workers=STORE_FETCH_WORKERS) as pool:
        records = list(pool.map(one, slugs))
    return [r for r in records if r]


def _stores():
    return _memoised("stores", lambda: cached_call("kmart.stores_index", {}, _stores_record, ttl.STORES_CACHE))


# ---- listing plumbing ------------------------------------------------------------------

def _filters(data, group_id=None):
    """The shared listing params -> Constructor facet filters."""
    filters = {}
    if group_id and group_id != "all":
        filters["group_id"] = group_id
    if data.get("brand"):
        filters["Brand"] = data["brand"]
    if data.get("colour"):
        filters["Colour"] = data["colour"]
    if data.get("size"):
        filters["Size"] = data["size"]
    if data.get("seller"):
        filters["Shops"] = _seller_name(data["seller"])
    lo, hi = data.get("min_price"), data.get("max_price")
    if lo is not None or hi is not None:
        filters["Price"] = f"{parsers.number(lo) if lo is not None else 0}-{parsers.number(hi) if hi is not None else 1000000}"
    if data.get("state"):
        filters[f"Available in {data['state'].upper()}"] = "True"
    for param, facet in (("clearance", "clearance"), ("online_only", "onlineOnly"), ("onepass", "onepassEligible")):
        if data.get(param) is not None:
            filters[facet] = "True" if data[param] else "False"
    return filters


def _sort(data):
    return SORTS.get(data.get("sort") or "popular")


def _empty_listing(page, per_page):
    return {"results": [], "category": None, "facets": [], "availability_by_state": None,
            "sort_options": [], "related_searches": None, "match_sources": None,
            "pagination": {"page": page, "items_per_page": per_page, "has_next": False,
                           "total_pages": None, "total_count": None}}


def _browse(kind, value, data, group_id=None, extra_filters=None):
    page, per_page = data["page"], data["limit"]
    if (page - 1) * per_page >= RESULT_WINDOW:
        return _empty_listing(page, per_page)
    filters = _filters(data, group_id)
    filters.update(extra_filters or {})
    try:
        payload = fetch_browse(kind, value, page, per_page, filters, _sort(data))
    except KmartBadRequest:
        if page > 1:   # a page the engine will not serve is an empty page, not an error
            return _empty_listing(page, per_page)
        raise
    return parsers.parse_listing(payload, page, per_page)


def _listing_response(listing, **head):
    out = dict(head)
    out.update(listing)
    return out


# ---- products/search ------------------------------------------------------------------

def _products_search(**data):
    page, per_page = data["page"], data["limit"]
    if (page - 1) * per_page >= RESULT_WINDOW:
        return _listing_response(_empty_listing(page, per_page), query=data["query"])
    target = _resolve_category(data.get("category"))
    group_id = target[1] if target and target[0] == "group" else None
    filters = _filters(data, group_id)
    if target and target[0] == "collection":
        raise ValueError("search within a collection is not supported; pass a category link or id.")
    try:
        payload = fetch_search(data["query"], page, per_page, filters, _sort(data))
    except KmartBadRequest:
        if page > 1:
            return _listing_response(_empty_listing(page, per_page), query=data["query"])
        raise
    return _listing_response(parsers.parse_listing(payload, page, per_page), query=data["query"])


def products_search(**data):
    return cached_call("kmart.search", data, _products_search, ttl.SEARCH_CACHE)


# ---- products/details, products/bulk ----------------------------------------------------

def _with_categories(record):
    record["category"] = _category_ref(record.get("category_id"))
    record["categories"] = [_category_ref(g) for g in record.get("category_ids") or []]
    return record


def _product_details(product):
    payload = fetch_items([constructor_item_id(product)])
    results = ((payload.get("response") or {}).get("results")) or []
    if not results:
        raise KmartNotFound(f"product {product} not found")
    return _with_categories(parsers.parse_product(results[0]))


def product_details(**data):
    return cached_call("kmart.product", data, _product_details, ttl.PRODUCT_CACHE)


def _products_bulk(products):
    payload = fetch_items([constructor_item_id(p) for p in products])
    results = [parsers.parse_product(r) for r in ((payload.get("response") or {}).get("results")) or []]
    found = {r["id"] for r in results}
    order = {p: i for i, p in enumerate(products)}
    results.sort(key=lambda r: order.get(r["id"], len(order)))
    return {
        "count": len(results),
        "results": [_with_categories(r) for r in results],
        "missing": [p for p in products if p not in found],
    }


def products_bulk(**data):
    return cached_call("kmart.products_bulk", data, _products_bulk, ttl.PRODUCT_CACHE)


# ---- products/reviews ------------------------------------------------------------------

def _product_reviews(product, sort, rating, page, limit):
    # Constructor first: it owns the keycode -> product link / image mapping
    # and decides "unknown keycode" (Yotpo answers unknown keycodes and
    # review-less marketplace items the same way: no product, no reviews).
    items = ((fetch_items([constructor_item_id(product)]).get("response") or {}).get("results")) or []
    if not items:
        raise KmartNotFound(f"product {product} not found")
    record = parsers.parse_product(items[0], compact=True)
    payload = fetch_reviews(product, page, limit, REVIEW_SORTS.get(sort), rating)
    out = parsers.parse_reviews(payload, page, limit, star=rating)
    out["product"] = {"id": record["id"], "name": record["name"], "link": record["link"],
                      "image": record["image"], "brand": record["brand"]}
    if parsers.reviews_product_missing(payload):
        out["summary"]["average"] = record["rating"]["average"] or None
        out["summary"]["count"] = record["rating"]["count"] or 0
        out["pagination"]["total_count"] = 0 if rating else (record["rating"]["count"] or 0)
    return out


def product_reviews(**data):
    return cached_call("kmart.reviews", data, _product_reviews, ttl.REVIEWS_CACHE)


# ---- products/suggestions ----------------------------------------------------------------

def _products_suggestions(query, limit):
    out = parsers.parse_autocomplete(fetch_autocomplete(query, products=limit))
    out["products"] = out["products"][:limit]
    return {"query": query, **out}


def products_suggestions(**data):
    return cached_call("kmart.suggestions", data, _products_suggestions, ttl.SUGGESTIONS_CACHE)


# ---- products/bestsellers ----------------------------------------------------------------

def _products_bestsellers(category, limit):
    target = _resolve_category(category)
    filters = {}
    if target and target[0] == "group" and target[1] != "all":
        filters["group_id"] = target[1]
    elif target and target[0] == "collection":
        raise ValueError("bestsellers take a category, not a collection.")
    out = parsers.parse_recommendations(fetch_recommendations(BESTSELLERS_POD, limit, filters))
    out["results"] = out["results"][:limit]
    out["count"] = len(out["results"])
    return {"category": _category_ref(filters.get("group_id")), **out}


def products_bestsellers(**data):
    return cached_call("kmart.bestsellers", data, _products_bestsellers, ttl.BESTSELLERS_CACHE)


# ---- categories -------------------------------------------------------------------------

def _categories(category, depth):
    target = _resolve_category(category)
    if target[0] == "collection":
        raise ValueError("a collection has no sub-categories; use /kmart/categories/products for its items.")
    by_id, _ = _tree_index()
    node = _tree() if target[1] == "all" else by_id[target[1]]
    return parsers.parse_category_tree(node, depth)


def categories(**data):
    return cached_call("kmart.categories", data, _categories, ttl.TREE_CACHE)


def _category_products(**data):
    kind, value = _resolve_category(data["category"])
    if kind == "collection":
        listing = _browse("collection_id", value, data)   # a 404 from Constructor = unknown collection
        return _listing_response(listing, collection={"slug": value, "link": f"{SITE}/collection/{value}/"})
    listing = _browse("group_id", value, data)
    if listing.get("category") is None:
        listing["category"] = _category_ref(value)
    return listing


def category_products(**data):
    return cached_call("kmart.category_products", data, _category_products, ttl.LISTING_CACHE)


# ---- specials ---------------------------------------------------------------------------

SPECIAL_FILTERS = {
    "clearance": {"clearance": "True"},
    "online_only": {"onlineOnly": "True"},
    "onepass": {"onepassEligible": "True"},
    "new": {},
}


def _specials(**data):
    kind = data["type"]
    target = _resolve_category(data.get("category"))
    if target and target[0] == "collection":
        raise ValueError("specials take a category, not a collection.")
    group_id = target[1] if target else "all"
    if kind == "new":
        data = dict(data, sort="new")
    listing = _browse("group_id", group_id, data, extra_filters=SPECIAL_FILTERS[kind])
    return _listing_response(listing, type=kind)


def specials(**data):
    return cached_call("kmart.specials", data, _specials, ttl.LISTING_CACHE)


# ---- brands -----------------------------------------------------------------------------

def _brands(category, query):
    target = _resolve_category(category)
    if target and target[0] == "collection":
        raise ValueError("brands take a category, not a collection.")
    group_id = target[1] if target else "all"
    payload = _all_facets() if group_id == "all" else fetch_browse("group_id", group_id, page=1, per_page=1)
    facets = ((payload.get("response") or {}).get("facets")) or []
    brand = next((f for f in facets if (f or {}).get("name") == "Brand"), {}) or {}
    rows = [{"name": parsers.clean_str(o.get("value")), "product_count": parsers.to_int(o.get("count"))}
            for o in brand.get("options") or [] if (o or {}).get("value")]
    if query:
        needle = query.lower()
        rows = [r for r in rows if needle in r["name"].lower()]
    rows.sort(key=lambda r: (-(r["product_count"] or 0), r["name"].lower()))
    return {"category": _category_ref(group_id) if group_id != "all" else None,
            "count": len(rows), "brands": rows}


def brands(**data):
    return cached_call("kmart.brands", data, _brands, ttl.BRANDS_CACHE)


def _brand_products(**data):
    listing = _browse("Brand", data["brand"], data)
    if data["page"] == 1 and not listing["results"] and not listing["pagination"].get("total_count"):
        raise KmartNotFound(f"brand {data['brand']!r} not found (see /kmart/brands for the list)")
    return _listing_response(listing, brand=data["brand"])


def brand_products(**data):
    return cached_call("kmart.brand_products", data, _brand_products, ttl.LISTING_CACHE)


# ---- sellers ----------------------------------------------------------------------------

def _sellers_list(query):
    rows = _sellers()
    if query:
        needle = query.lower()
        rows = [r for r in rows if needle in (r["name"] or r["slug"]).lower()]
    return {"count": len(rows), "sellers": rows}


def sellers(**data):
    return cached_call("kmart.sellers", data, _sellers_list, ttl.SELLERS_CACHE)


def _seller_record(seller):
    record = parsers.parse_shop_page(fetch_shop_page(seller), seller)
    if not record:
        raise KmartNotFound(f"seller {seller} not found")
    return record


def seller_details(**data):
    return cached_call("kmart.seller", data, _seller_record, ttl.SELLERS_CACHE)


def _seller_products(**data):
    name = _seller_name(data["seller"])
    listing = _browse("Shops", name, dict(data, seller=None))
    return _listing_response(listing, seller={"slug": data["seller"], "name": name, "link": seller_link(data["seller"])})


def seller_products(**data):
    return cached_call("kmart.seller_products", data, _seller_products, ttl.LISTING_CACHE)


# ---- stores -----------------------------------------------------------------------------

def _stores_search(location, state, page, limit):
    rows = parsers.rank_stores(_stores(), location, state.upper() if state else None)
    total = len(rows)
    start = (page - 1) * limit
    return {
        "location": location,
        "state": state.upper() if state else None,
        "results": rows[start:start + limit],
        "pagination": parsers.pagination(page, limit, total, window=10 ** 9),
    }


def stores_search(**data):
    return cached_call("kmart.stores_search", data, _stores_search, ttl.STORES_CACHE)


def _store_details(store):
    if store.startswith("id:"):
        wanted = int(store[3:])
        for row in _stores():
            if row["id"] == wanted:
                return row
        raise KmartNotFound(f"store number {wanted} not found")
    return _store(store)


def store_details(**data):
    return _store_details(data["store"])


# ---- sitemaps ---------------------------------------------------------------------------

def _sitemap_index():
    rows = parsers.parse_sitemap_index(fetch_sitemap())
    return {"link": f"{SITE}/sitemap.xml", "count": len(rows), "sitemaps": rows}


def sitemap_index(**data):
    return cached_call("kmart.sitemap_index", data, _sitemap_index, ttl.SITEMAP_CACHE)


def _sitemap_file(type, part):
    path = sitemap_path(type, part)
    return {"link": SITE + path, "rows": parsers.parse_sitemap_urls(fetch_sitemap(path))}


def _sitemap_links(type, part, page, limit):
    if type == "products" and not part:
        part = "a"
    if type != "products":
        part = None
    file = cached_call("kmart.sitemap_file", {"type": type, "part": part}, _sitemap_file, ttl.SITEMAP_CACHE)
    rows = file["rows"]
    start = (page - 1) * limit
    return {
        "type": type,
        "part": part,
        "sitemap": file["link"],
        "results": rows[start:start + limit],
        "pagination": parsers.pagination(page, limit, len(rows), window=10 ** 9),
    }


def sitemap_links(**data):
    return _sitemap_links(**data)
