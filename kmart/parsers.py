"""Kmart parsers: raw Constructor.io / Yotpo JSON, kmart.com.au Next.js
pages and sitemaps -> clean dicts. Pure functions, no I/O.

Fixtures (kmart/fixtures/, captured 2026-10-28 from the live site):

  cnstrc_search_towel_p1.json           search/towel page 1, 40 results, hidden fields + facets
  cnstrc_search_towel_filtered.json     search/towel with Colour + Price filters, sorted by price
  cnstrc_search_nomatch.json            search/zzqqxxyyzz: 0 keyword matches, 100 semantic fallbacks
  cnstrc_items_three.json               browse/items: a Kmart towel (348 reviews), a 12-variant
                                        clearance set with per-state stock-outs, a Target T-shirt
                                        (59 variants, marketplace offer)
  cnstrc_items_missing.json             browse/items for an unknown id: zero results
  cnstrc_groups_full.json               browse/groups, full depth: the whole category tree
  cnstrc_browse_group_bath_towels_p1.json   browse/group_id/<Bath Towels>
  cnstrc_browse_group_unknown.json      browse/group_id/deadbeef: zero results, no groups
  cnstrc_browse_collection_wireless_headphones.json   browse/collection_id/<slug>
  cnstrc_browse_collection_unknown.json  the 404 body for an unknown collection
  cnstrc_browse_brand_anko_p1.json      browse/Brand/Anko
  cnstrc_browse_brand_unknown.json      browse/Brand/<unknown>: zero results
  cnstrc_browse_shop_target_p1.json     browse/Shops/Target
  cnstrc_browse_clearance_p1.json       browse/group_id/all with filters[clearance]=True
  cnstrc_browse_all_facets.json         browse/group_id/all, 1 result: every facet (Brand, Shops…)
  cnstrc_autocomplete_tow.json          autocomplete/tow: Search Suggestions + Products
  cnstrc_autocomplete_nomatch.json      autocomplete for a nonsense term
  cnstrc_bestsellers.json               recommendations pod bestsellers_products, 10 results
  cnstrc_bestsellers_group.json         the same pod filtered to one group
  yotpo_reviews_42442493_p1.json        Yotpo widget reviews, page 1 of 348, newest first
  yotpo_reviews_42442493_star5_images.json   star=5, most voted
  yotpo_reviews_unknown.json            an unknown keycode: no product, no reviews
  store_mandurah.html                   /store-detail/mandurah/ (Next.js page, __NEXT_DATA__)
  store_unknown_404.html                the head of the site's 404 page
  shop_target.html, shop_abm_global.html   /shop/<slug>/ pages
  shop_unknown_404.html                 the head of the site's 404 page
  sitemap_index.xml, sitemap_seller.xml, sitemap_storelocation.xml, sitemap_collection.xml,
  sitemap_content.xml, sitemap_product_i_head300.xml, sitemap_category_head300.xml
"""
import html as html_lib
import json
import math
import re
from datetime import date

from kmart.refs import (AU_STATES, SITE, keycode_from_item_id, product_link, seller_link,
                        seller_slug, store_link, store_slug_from_link)

CURRENCY = "AUD"
IMAGE_CDN = "https://assets.kmart.com.au/transform/"
IMAGE_SUFFIX = "?io=transform:extend,width:580,height:725"
RESULT_WINDOW = 10000   # Constructor serves no result past the 10,000th

# Our sort names -> Constructor (sort_by, sort_order); the site's own four.
SORTS = {
    "popular": ("relevance", "descending"),
    "new": ("numberOfDaysSinceStartDate", "ascending"),
    "price_asc": ("price", "ascending"),
    "price_desc": ("price", "descending"),
}
_SORT_NAMES = {v: k for k, v in SORTS.items()}

# Facets that are internal plumbing, never shown.
_NOISE_FACETS = {"__cnstrc_age", "stateOOS"}
_STATE_FACET_RE = re.compile(r"^Available in ([A-Z]{2,3})$")

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)


# ---- value helpers --------------------------------------------------------------

def to_float(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def to_int(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    match = re.search(r"-?\d+", str(value).replace(",", ""))
    return int(match.group(0)) if match else None


def to_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    low = str(value).strip().lower()
    if low in ("true", "1", "yes"):
        return True
    if low in ("false", "0", "no"):
        return False
    return None


def clean_str(value):
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def number(value):
    """A price-like value as int when whole, else float (9.0 -> 9, 2.5 -> 2.5)."""
    value = to_float(value)
    if value is None:
        return None
    return int(value) if value == int(value) else value


def iso_date(value):
    """'2026-09-30T18:42:09.000Z' / '2026-09-30' -> '2026-09-30'; the catalogue's
    sentinel dates (9999-12-31 open end, 1899-12-30 / 2000-01-01 unset) -> None."""
    text = clean_str(value)
    if not text:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    if not match:
        return None
    text = match.group(1)
    if text in ("9999-12-31", "1899-12-30", "2000-01-01"):
        return None
    return text


def iso_datetime(value):
    text = clean_str(value)
    if not text:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})", text)
    return f"{match.group(1)}T{match.group(2)}Z" if match else iso_date(text)


def html_to_text(markup):
    """The PDP description HTML -> readable text (lists as '- ' lines)."""
    if not markup:
        return None
    text = str(markup)
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*/?\s*(p|div|ul|ol|h\d|tr|table)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*li[^>]*>", "- ", text, flags=re.I)
    text = re.sub(r"<\s*/\s*li\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    lines = [" ".join(line.split()) for line in text.split("\n")]
    out = "\n".join(line for line in lines if line)
    return out or None


def image_link(path):
    """Constructor's altImages are CDN paths ('<uuid>/<keycode>-2'); image_url
    is already absolute."""
    if not path:
        return None
    path = str(path)
    if path.startswith("http"):
        return path
    return IMAGE_CDN + path.lstrip("/") + IMAGE_SUFFIX


def pagination(page, per_page, total, window=RESULT_WINDOW):
    """The block route_glue.paginate lifts into the flat gateway shape;
    total_pages is capped at what the upstream will actually serve."""
    total = to_int(total) or 0
    per_page = max(int(per_page or 1), 1)
    pages = math.ceil(total / per_page) if total else 0
    served = math.ceil(min(total, window) / per_page) if total else 0
    return {"page": page, "items_per_page": per_page, "total_pages": min(pages, served),
            "total_count": total}


# ---- products (Constructor result records) ----------------------------------------

def parse_state_oos(value):
    """stateOOS is a {state: "6"} map (6 = out of stock) or null / '{}' ->
    the sorted list of states the item is out of stock in."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if not isinstance(value, dict):
        return []
    return sorted(state for state in value if state in AU_STATES)


def _badge_texts(*groups):
    """badges / variant_badges are plain strings; badgesMarketplace /
    variant_badges_marketplace are {type: [{displayText}]} maps."""
    out = []
    for group in groups:
        if isinstance(group, list):
            for item in group:
                text = clean_str(item if isinstance(item, str) else (item or {}).get("displayText"))
                if text and text not in out:
                    out.append(text)
        elif isinstance(group, dict):
            for kind, items in group.items():
                if kind == "seller" or not isinstance(items, list):
                    continue
                for item in items:
                    text = clean_str((item or {}).get("displayText"))
                    if text and text not in out:
                        out.append(text)
    return out


def _seller_badge(data):
    """badgesMarketplace.seller[0] -> {id, name}; id 1 = Kmart, 2000 = Target."""
    badge = ((data.get("badgesMarketplace") or {}).get("seller") or [{}])[0] or {}
    seller_id = to_int(badge.get("id"))
    offers = data.get("offers") or []
    name = None
    for offer in offers:
        if to_int((offer or {}).get("shopId")) == seller_id:
            name = clean_str(offer.get("shopName"))
            break
    if name is None:
        text = clean_str(badge.get("displayText"))
        name = {"kmart-target": "Kmart", "kmart": "Kmart", "target": "Target"}.get(
            (text or "").lower(), text.title() if text else None)
    if seller_id is None and name is None:
        return None
    return {"id": seller_id, "name": name}


def parse_offer(offer):
    offer = offer or {}
    extra = {clean_str((f or {}).get("code")): (f or {}).get("value")
             for f in offer.get("offerAdditionalFields") or []}
    prices = offer.get("prices") or [{}]
    return {
        "id": to_int(offer.get("id")),
        "seller": {"id": to_int(offer.get("shopId")), "name": clean_str(offer.get("shopName"))},
        "price": number((prices[0] or {}).get("originPrice")),
        "currency": CURRENCY,
        "stock_quantity": to_int(offer.get("quantity")),
        "is_cheapest": to_bool(offer.get("cheapestOffer")),
        "has_fastest_delivery": to_bool(offer.get("fastestDelivery")),
        "is_onepass_eligible": to_bool(extra.get("onepasseligible")),
        "fulfilment_channel": to_int(offer.get("fulfilmentChannel")),
    }


def parse_pricing(data, today=None):
    """price / prices / SavePrice -> one pricing block. `prices` carries the
    list price (open-ended) and the latest promo window; SavePrice is the
    site's "WAS $11" strike-through label."""
    today = today or date.today().isoformat()
    price = number(data.get("price"))
    list_price = None
    promo = None
    for row in data.get("prices") or []:
        row = row or {}
        kind = (row.get("type") or "").lower()
        if kind == "list":
            list_price = number(row.get("amount"))
        elif kind == "promo":
            candidate = {
                "price": number(row.get("amount")),
                "starts": iso_date(row.get("startDate")),
                "ends": iso_date(row.get("endDate")),
            }
            candidate["is_active"] = bool(
                candidate["starts"] and candidate["starts"] <= today
                and (candidate["ends"] is None or candidate["ends"] >= today))
            if promo is None or (candidate["starts"] or "") > (promo["starts"] or ""):
                promo = candidate
    was_price = number(data.get("SavePrice"))
    return {
        "price": price,
        "currency": CURRENCY,
        "list_price": list_price,
        "was_price": was_price,
        "is_on_sale": bool(was_price is not None and price is not None and was_price > price),
        "promotion": promo,
    }


def parse_variant(variation):
    variation = variation or {}
    data = variation.get("data") or {}
    images = [data.get("image_url")] + [image_link(p) for p in data.get("altImages") or []]
    return {
        "id": clean_str(data.get("variation_id")),
        "name": clean_str(variation.get("value")),
        "colour": clean_str(data.get("Colour")),
        "secondary_colour": clean_str(data.get("SecondaryColour")),
        "size": clean_str(data.get("Size")),
        "barcode": clean_str(data.get("apn")),
        "image": data.get("image_url") or None,
        "images": [i for i in images if i],
        "pricing": parse_pricing(data),
        "sold_by": [s for s in data.get("Seller") or [] if s] or None,
        "offers": [parse_offer(o) for o in data.get("offers") or []],
        "badges": _badge_texts(data.get("variant_badges"), data.get("variant_badges_marketplace")),
        "is_default": to_bool(data.get("is_default")),
        "is_clearance": to_bool(data.get("clearance")),
        "out_of_stock_states": parse_state_oos(data.get("stateOOS")),
    }


def compact_variant(variant):
    out = {k: variant[k] for k in ("id", "colour", "size", "barcode", "image")}
    out["price"] = variant["pricing"]["price"]
    for key in ("is_default", "is_clearance", "out_of_stock_states"):
        out[key] = variant[key]
    return out


def parse_product(result, compact=False):
    """One Constructor result record ({value, data, variations}) -> the
    product. compact=True (listings) drops the description and keeps a
    short variant row (id / colour / size / price)."""
    result = result or {}
    data = result.get("data") or {}
    keycode = keycode_from_item_id(data.get("id"))
    ratings = data.get("ratings") or {}
    variants = [parse_variant(v) for v in result.get("variations") or []]
    images = [data.get("image_url")] + [image_link(p) for p in data.get("altImages") or []]
    sold_by = [s for s in data.get("Seller") or [] if s]
    seller = _seller_badge(data)
    record = {
        "id": keycode or None,
        "name": clean_str(result.get("value")),
        "link": product_link(data.get("url") or data.get("uri") or keycode),
        "brand": clean_str(data.get("Brand")),
        "image": data.get("image_url") or None,
        "images": [i for i in images if i],
        "video": data.get("video") or None,
        "pricing": parse_pricing(data),
        "rating": {
            "average": to_float(ratings.get("averageScore")),
            "count": to_int(ratings.get("totalReviews")),
        },
        "colour": clean_str(data.get("Colour")),
        "secondary_colour": clean_str(data.get("SecondaryColour")),
        "size": clean_str(data.get("Size")),
        "barcode": clean_str(data.get("apn")),
        "badges": _badge_texts(data.get("badges"), data.get("variant_badges"),
                               data.get("badgesMarketplace"), data.get("variant_badges_marketplace")),
        "seller": seller,
        "sold_by": sold_by or None,
        "is_marketplace": ("Marketplace" in sold_by) if sold_by else (
            bool(seller and seller["id"] not in (1, 2000)) if seller else None),
        "is_clearance": to_bool(data.get("clearance")),
        "is_assorted": to_bool(data.get("AssortedProducts")),
        "has_ar_view": to_bool(data.get("arEnabled")),
        "out_of_stock_states": parse_state_oos(data.get("stateOOS")),
        "shipping": {
            "is_free": to_bool(data.get("FreeShipping")),
            "is_free_metro": to_bool(data.get("FreeShippingMetro")),
            "is_flat_rate_big_bulky_metro": to_bool(data.get("flatRateBigBulkyMetro")),
            "has_national_inventory": to_bool(data.get("nationalInventory")),
            "fulfilment_channel": to_int(data.get("FulfilmentChannel")),
        },
        "pre_order": {
            "is_active": to_bool(data.get("isPreOrderActive")),
            "release_date": iso_date(data.get("preOrderReleaseDate")) if to_bool(data.get("isPreOrderActive")) else None,
        },
        "category_id": clean_str(data.get("primaryCategoryId")),
        "category_ids": [g for g in data.get("group_ids") or [] if g],
        "merchandise": {
            "department": to_int(data.get("MerchDepartment")),
            "class_name": clean_str(data.get("MerchClassName")),
        },
        "variant_count": len(variants),
    }
    if compact:
        record["variants"] = [compact_variant(v) for v in variants]
    else:
        record["description"] = html_to_text(data.get("description"))
        record["description_html"] = clean_str(data.get("description"))
        record["offers"] = [parse_offer(o) for o in data.get("offers") or []]
        record["variants"] = variants
    return record


# ---- listings (search / browse) ------------------------------------------------------

def parse_facet(facet):
    facet = facet or {}
    kind = facet.get("type")
    out = {
        "name": clean_str(facet.get("name")),
        "label": clean_str(facet.get("display_name")),
        "type": kind,
        "is_hidden": bool(facet.get("hidden")),
    }
    if kind == "range":
        out["min"] = number(facet.get("min"))
        out["max"] = number(facet.get("max"))
        out["options"] = None
    else:
        options = []
        for option in facet.get("options") or []:
            option = option or {}
            row = {
                "value": option.get("value"),
                "label": clean_str(option.get("display_name")),
                "count": to_int(option.get("count")),
                "is_selected": (option.get("status") == "selected"),
            }
            rng = option.get("range")
            if isinstance(rng, list) and len(rng) == 2:
                row["range"] = [None if v in ("-inf", "inf") else number(v) for v in rng]
            options.append(row)
        out["options"] = options
    return out


def parse_facets(facets):
    """Constructor facets -> (facets list, availability_by_state). The hidden
    'Available in <state>' facets become one {state: {available, unavailable}}
    map; __cnstrc_age / stateOOS are plumbing and dropped."""
    out, by_state = [], {}
    for facet in facets or []:
        name = (facet or {}).get("name") or ""
        if name in _NOISE_FACETS:
            continue
        match = _STATE_FACET_RE.match(name)
        if match:
            counts = {str(o.get("value")): to_int(o.get("count")) for o in facet.get("options") or []}
            by_state[match.group(1)] = {"available": counts.get("True", 0), "unavailable": counts.get("False", 0)}
            continue
        out.append(parse_facet(facet))
    return out, by_state


def parse_group(node, with_children=True):
    """One node of Constructor's groups (the category tree / a listing's
    group breakdown)."""
    node = node or {}
    data = node.get("data") or {}
    url = data.get("url")
    out = {
        "id": clean_str(node.get("group_id")),
        "name": clean_str(node.get("display_name")),
        "link": (SITE + url) if url and url.startswith("/") else None,
        "product_count": to_int(node.get("count")),
        "is_special": to_bool(data.get("isSpecial")),
        "path": [clean_str(p.get("display_name")) for p in node.get("parents") or [] if p and p.get("group_id") != "all"],
    }
    if with_children:
        out["children"] = [parse_group(c, with_children=False) for c in node.get("children") or []]
    return out


def parse_sort_options(options):
    out = []
    for option in options or []:
        option = option or {}
        key = (option.get("sort_by"), option.get("sort_order"))
        out.append({
            "value": _SORT_NAMES.get(key, f"{key[0]}:{key[1]}"),
            "label": clean_str(option.get("display_name")),
            "is_selected": option.get("status") == "selected",
        })
    return out


def parse_listing(payload, page, per_page):
    """search / browse payload -> results + facets + categories + pagination."""
    payload = payload or {}
    resp = payload.get("response") or {}
    results = [parse_product(r, compact=True) for r in resp.get("results") or []]
    facets, by_state = parse_facets(resp.get("facets"))
    groups = resp.get("groups") or []
    current = parse_group(groups[0]) if groups else None
    sources = resp.get("result_sources") or {}
    out = {
        "results": results,
        "category": current,
        "facets": facets,
        "availability_by_state": by_state or None,
        "sort_options": parse_sort_options(resp.get("sort_options")),
        "related_searches": [clean_str(r.get("term") if isinstance(r, dict) else r)
                             for r in resp.get("related_searches") or []] or None,
        "match_sources": {
            "keyword": to_int((sources.get("token_match") or {}).get("count")),
            "semantic": to_int((sources.get("embeddings_match") or {}).get("count")),
        } if sources else None,
        "pagination": pagination(page, per_page, resp.get("total_num_results")),
    }
    return out


def listing_is_empty(payload):
    """A browse of an unknown group / brand / shop answers 200 with no
    results and no groups — distinguishes "unknown" from a real empty page."""
    resp = (payload or {}).get("response") or {}
    return not resp.get("results") and not resp.get("groups") and not to_int(resp.get("total_num_results"))


# ---- category tree ----------------------------------------------------------------------

def parse_tree(payload):
    """browse/groups payload -> the root node (raw Constructor shape)."""
    groups = ((payload or {}).get("response") or {}).get("groups") or []
    return groups[0] if groups else None


def walk_tree(node, depth=0):
    yield node, depth
    for child in (node or {}).get("children") or []:
        yield from walk_tree(child, depth + 1)


def index_tree(root):
    """{group id: node} and {site path: group id} for link resolution."""
    by_id, by_path = {}, {}
    for node, _ in walk_tree(root):
        gid = node.get("group_id")
        if not gid:
            continue
        by_id[gid] = node
        url = (node.get("data") or {}).get("url")
        if url:
            path = "/" + url.strip("/").lower() + "/"
            by_path.setdefault(path, gid)
    return by_id, by_path


def parse_category_tree(node, depth, _level=0):
    """A node -> {id, name, link, product_count, children…} to `depth` levels."""
    out = parse_group(node, with_children=False)
    out["children_count"] = len(node.get("children") or [])
    if _level < depth:
        out["children"] = [parse_category_tree(c, depth, _level + 1) for c in node.get("children") or []]
    else:
        out["children"] = None
    return out


# ---- autocomplete -------------------------------------------------------------------------

def parse_autocomplete(payload):
    sections = (payload or {}).get("sections") or {}
    suggestions = []
    for row in sections.get("Search Suggestions") or []:
        data = (row or {}).get("data") or {}
        suggestions.append({
            "term": clean_str(row.get("value") or data.get("id")),
            "product_count": to_int(data.get("total_num_results")),
            "image": data.get("image_url") or None,
            "categories": [{"id": clean_str(g.get("group_id")), "name": clean_str(g.get("display_name"))}
                           for g in data.get("groups") or []],
        })
    products = [parse_product(r, compact=True) for r in sections.get("Products") or []]
    return {"suggestions": suggestions, "products": products}


# ---- recommendations ----------------------------------------------------------------------

def parse_recommendations(payload):
    resp = (payload or {}).get("response") or {}
    pod = resp.get("pod") or {}
    return {
        "pod": {"id": clean_str(pod.get("id")), "name": clean_str(pod.get("display_name"))},
        "results": [parse_product(r, compact=True) for r in resp.get("results") or []],
        "count": to_int(resp.get("total_num_results")),
    }


# ---- Yotpo reviews ------------------------------------------------------------------------

def _custom_ratings(fields):
    out = {}
    for row in (fields or {}).values():
        row = row or {}
        title = clean_str(row.get("title"))
        if not title:
            continue
        value = row.get("value", row.get("average_score", row.get("score")))
        out[title] = number(value)
    return out or None


def _review_images(images):
    out = []
    for item in images or []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            link = item.get("image_url") or item.get("original_url") or item.get("thumb_url")
            if link:
                out.append(link)
    return out


def parse_review(review):
    review = review or {}
    user = review.get("user") or {}
    comment = review.get("comment") or None
    return {
        "id": to_int(review.get("id")),
        "title": clean_str(review.get("title")),
        "content": clean_str(review.get("content")),
        "rating": to_int(review.get("score")),
        "date": iso_datetime(review.get("created_at")),
        "author": {"id": to_int(user.get("user_id")), "name": clean_str(user.get("display_name"))},
        "is_verified_buyer": to_bool(review.get("verified_buyer")),
        "is_incentivized": to_bool(review.get("is_incentivized")),
        "incentive_type": clean_str(review.get("incentive_type")),
        "votes": {"up": to_int(review.get("votes_up")), "down": to_int(review.get("votes_down"))},
        "sentiment": to_float(review.get("sentiment")),
        "ratings_breakdown": _custom_ratings(review.get("custom_fields")),
        "images": _review_images(review.get("images_data")),
        "reply": {"content": clean_str(comment.get("content")), "date": iso_datetime(comment.get("created_at"))}
        if isinstance(comment, dict) else None,
        "language": clean_str(review.get("language")),
    }


def parse_reviews(payload, page, per_page, star=None):
    """Yotpo's pagination.total is the unfiltered count even under a star
    filter; the bottomline star_distribution gives the filtered total."""
    resp = (payload or {}).get("response") or {}
    bottom = resp.get("bottomline") or {}
    products = resp.get("products") or []
    product = (products[0] or {}) if products else {}
    paging = resp.get("pagination") or {}
    stars = bottom.get("star_distribution") or {}
    total = paging.get("total")
    if star and stars:
        total = stars.get(str(star), 0)
    return {
        "product": {
            "id": clean_str(product.get("domain_key")),
            "name": clean_str(product.get("name")),
            "image": product.get("image_url") or None,
        } if product else None,
        "summary": {
            "average": to_float(bottom.get("average_score")),
            "count": to_int(bottom.get("total_review")),
            "star_distribution": {str(k): to_int(v) for k, v in sorted(stars.items())} if stars else None,
            "ratings_breakdown": _custom_ratings(bottom.get("custom_fields_bottomline")),
        },
        "reviews": [parse_review(r) for r in resp.get("reviews") or []],
        "pagination": pagination(page, per_page, total, window=10 ** 9),
    }


def reviews_product_missing(payload):
    """Yotpo answers an unknown keycode with no product record."""
    resp = (payload or {}).get("response") or {}
    return not resp.get("products")


# ---- kmart.com.au Next.js pages ----------------------------------------------------------

def next_data(html):
    """The __NEXT_DATA__ JSON of a server-rendered page (None when absent)."""
    match = _NEXT_DATA_RE.search(html or "")
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except ValueError:
        return None


def page_props(html):
    data = next_data(html) or {}
    return ((data.get("props") or {}).get("pageProps")) or {}


_HOURS_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([AP]M)\s*-\s*(\d{1,2})(?::(\d{2}))?\s*([AP]M)", re.I)


def _clock(hour, minute, ampm):
    hour = int(hour) % 12 + (12 if ampm.upper() == "PM" else 0)
    return f"{hour:02d}:{int(minute or 0):02d}"


def parse_trading_hours(rows):
    out = []
    for row in rows or []:
        row = row or {}
        text = clean_str(row.get("hours"))
        match = _HOURS_RE.search(text or "")
        out.append({
            "day": clean_str(row.get("weekDay")).title() if row.get("weekDay") else None,
            "hours": text,
            "opens": _clock(match.group(1), match.group(2), match.group(3)) if match else None,
            "closes": _clock(match.group(4), match.group(5), match.group(6)) if match else None,
            "is_closed": bool(text and not match and "closed" in text.lower()),
        })
    return out


def parse_store_page(html, slug=None):
    """/store-detail/<slug>/ -> the store record (None when the page carries
    no location, i.e. not a store page)."""
    props = page_props(html)
    loc = props.get("location") or {}
    if not loc:
        return None
    schema = props.get("localBusinessSchema") or {}
    slug = slug or store_slug_from_link(schema.get("url"))
    address = [clean_str(loc.get(k)) for k in ("address1", "address2", "address3")]
    return {
        "id": to_int(loc.get("locationId")),
        "name": clean_str(loc.get("publicName")),
        "slug": slug,
        "link": store_link(slug) if slug else clean_str(schema.get("url")),
        "phone": clean_str(loc.get("phoneNumber")),
        "address": {
            "lines": [a for a in address if a],
            "suburb": clean_str(loc.get("city")),
            "state": clean_str(loc.get("state")),
            "postcode": clean_str(loc.get("postcode")),
            "country": clean_str((schema.get("address") or {}).get("addressCountry")) or "AU",
        },
        "location": {"latitude": to_float(loc.get("latitude")), "longitude": to_float(loc.get("longitude"))},
        "trading_hours": parse_trading_hours(loc.get("tradingHours")),
        "map_image": props.get("staticMapUrl") or None,
    }


def parse_shop_page(html, slug=None):
    """/shop/<slug>/ -> the seller record (None when the page has no shop)."""
    props = page_props(html)
    shop = props.get("shop") or {}
    if not shop:
        return None
    listing = (props.get("productResultStructure") or {}).get("response") or {}
    groups = listing.get("groups") or []
    slug = slug or clean_str(shop.get("slug"))
    return {
        "id": to_int(shop.get("id")),
        "name": clean_str(shop.get("name")),
        "slug": slug,
        "link": seller_link(slug) if slug else None,
        "logo": clean_str(shop.get("logo")),
        "description": clean_str(shop.get("description")),
        "shipping_policy": clean_str(shop.get("shippingPolicy")),
        "product_count": to_int(listing.get("total_num_results")),
        "categories": [parse_group(c, with_children=False) for c in (groups[0].get("children") if groups else []) or []],
        "is_onepass_shop": to_bool(shop.get("isOnePassShop")),
        "is_featured": to_bool(shop.get("isFeatured")),
        "is_marketplace_shop": to_bool(shop.get("isMarketplaceShop")),
        "has_badge": to_bool(shop.get("hasBadge")),
        "has_product_listing": to_bool(shop.get("hasProductListing")),
        "has_storefront": to_bool(shop.get("hasStoreFront")),
        "display_order": to_int(shop.get("displayOrder")),
    }


def page_title(html):
    match = _TITLE_RE.search(html or "")
    return clean_str(match.group(1)) if match else None


# ---- sellers index ---------------------------------------------------------------------------

def parse_seller_index(facets_payload, sitemap_rows):
    """The 'Shops' facet (every seller with live stock + count) joined with
    the seller sitemap (every seller with a /shop/ page + lastmod)."""
    facets = ((facets_payload or {}).get("response") or {}).get("facets") or []
    shops = next((f for f in facets if (f or {}).get("name") == "Shops"), {}) or {}
    rows = {}
    for option in shops.get("options") or []:
        name = clean_str((option or {}).get("value"))
        if not name:
            continue
        slug = seller_slug(name)
        rows[slug] = {"slug": slug, "name": name, "link": seller_link(slug),
                      "product_count": to_int(option.get("count")), "has_shop_page": False,
                      "page_updated": None}
    for entry in sitemap_rows or []:
        slug = entry.get("slug")
        if not slug:
            continue
        row = rows.setdefault(slug, {"slug": slug, "name": None, "link": seller_link(slug),
                                     "product_count": None, "has_shop_page": False, "page_updated": None})
        row["has_shop_page"] = True
        row["page_updated"] = entry.get("last_modified")
    for row in rows.values():
        if not row["has_shop_page"]:   # Kmart's own range and a few sellers have no /shop/ page
            row["link"] = None
    return sorted(rows.values(), key=lambda r: (-(r["product_count"] or 0), r["slug"]))


# ---- sitemaps -------------------------------------------------------------------------------

_SITEMAP_ENTRY_RE = re.compile(r"<(sitemap|url)>(.*?)</\1>", re.S)
_TAG_RE = re.compile(r"<(loc|lastmod|changefreq|priority)>\s*([^<]*?)\s*</\1>")
_SITEMAP_KIND_RE = re.compile(r"/([a-z]+)-sitemap(?:-([a-z]))?\.xml$")
_KIND_NAMES = {"product": "products", "category": "categories", "collection": "collections",
               "seller": "sellers", "storelocation": "stores", "content": "content"}


def _sitemap_entries(xml):
    for _, body in _SITEMAP_ENTRY_RE.findall(xml or ""):
        yield {k: html_lib.unescape(v) for k, v in _TAG_RE.findall(body)}


def parse_sitemap_index(xml):
    out = []
    for entry in _sitemap_entries(xml):
        link = entry.get("loc")
        if not link:
            continue
        match = _SITEMAP_KIND_RE.search(link)
        out.append({
            "type": _KIND_NAMES.get(match.group(1), match.group(1)) if match else None,
            "part": match.group(2) if match else None,
            "link": link,
            "last_modified": iso_date(entry.get("lastmod")),
        })
    return out


def _sitemap_identity(link):
    path = link[len(SITE):] if link.startswith(SITE) else link
    if "/product/" in path:
        match = re.search(r"/product/(?:(.*?)-)?(S?\d{5,10})/?$", path, re.I)
        if match:
            return {"id": match.group(2).upper(), "slug": match.group(1) or None}
    for marker in ("/store-detail/", "/shop/", "/collection/"):
        if marker in path:
            return {"slug": path.split(marker, 1)[1].strip("/") or None}
    if path.startswith("/category/"):
        return {"path": path}
    return {}


def parse_sitemap_urls(xml):
    out = []
    for entry in _sitemap_entries(xml):
        link = entry.get("loc")
        if not link:
            continue
        row = {"link": link}
        row.update(_sitemap_identity(link))
        row["last_modified"] = iso_date(entry.get("lastmod"))
        row["change_frequency"] = clean_str(entry.get("changefreq"))
        row["priority"] = to_float(entry.get("priority"))
        out.append(row)
    return out


# ---- stores index / search -----------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


_LATLNG_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def parse_location_query(text):
    """'-33.87,151.21' -> ('coords', (lat, lng)); '2000' -> ('postcode', '2000');
    anything else -> ('text', lower-cased words)."""
    text = (text or "").strip()
    match = _LATLNG_RE.match(text)
    if match:
        return "coords", (float(match.group(1)), float(match.group(2)))
    if re.fullmatch(r"\d{4}", text):
        return "postcode", text
    return "text", " ".join(text.lower().split())


def rank_stores(stores, location=None, state=None):
    """Filter / rank the store index for one query. Coordinates rank by
    distance (adds distance_km); a postcode ranks by postcode proximity
    (exact first, then numeric distance within the state's range); text
    matches name / suburb / address."""
    rows = [dict(s) for s in stores or []]
    if state:
        rows = [s for s in rows if (s.get("address") or {}).get("state") == state]
    if not location:
        return sorted(rows, key=lambda s: ((s.get("address") or {}).get("state") or "", s.get("name") or ""))
    kind, value = parse_location_query(location)
    if kind == "coords":
        lat, lng = value
        for s in rows:
            loc = s.get("location") or {}
            if loc.get("latitude") is not None and loc.get("longitude") is not None:
                s["distance_km"] = round(haversine_km(lat, lng, loc["latitude"], loc["longitude"]), 1)
            else:
                s["distance_km"] = None
        return sorted(rows, key=lambda s: (s["distance_km"] is None, s["distance_km"] or 0))
    if kind == "postcode":
        target = int(value)
        scored = []
        for s in rows:
            postcode = to_int((s.get("address") or {}).get("postcode"))
            if postcode is None:
                continue
            gap = abs(postcode - target)
            if gap <= 150:   # same region: Australian postcodes step by locality
                scored.append((gap, s))
        return [s for _, s in sorted(scored, key=lambda t: (t[0], t[1].get("name") or ""))]
    words = value.split()
    hits = []
    for s in rows:
        hay = " ".join(filter(None, [s.get("name"), s.get("slug"), (s.get("address") or {}).get("suburb"),
                                     " ".join((s.get("address") or {}).get("lines") or []),
                                     (s.get("address") or {}).get("state")])).lower()
        if all(w in hay for w in words):
            exact = (s.get("name") or "").lower() == value or ((s.get("address") or {}).get("suburb") or "").lower() == value
            hits.append((0 if exact else 1, s))
    return [s for _, s in sorted(hits, key=lambda t: (t[0], t[1].get("name") or ""))]
