"""Offline tests for the Kmart parsers, reference resolvers and value
helpers.

    python -m pytest kmart/test_parsers.py -q

Fixtures are real Constructor.io / Yotpo payloads and kmart.com.au pages
captured 2026-10-28 (kmart/fixtures/, listed in parsers.py's docstring):
a full-fat towel listing, three product records (Kmart own-range,
12-variant clearance set with per-state stock-outs, Target marketplace
listing), the whole category tree, unknown-id / unknown-brand / unknown
collection answers, reviews pages, a store page, two shop pages, the
site's 404 page and the sitemaps. No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kmart import parsers as P, refs  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


@pytest.fixture(scope="module")
def items():
    return fixture("cnstrc_items_three.json")["response"]["results"]


@pytest.fixture(scope="module")
def towel(items):
    return P.parse_product(items[0])


@pytest.fixture(scope="module")
def terry_set(items):
    return P.parse_product(items[1])


@pytest.fixture(scope="module")
def target_tee(items):
    return P.parse_product(items[2])


@pytest.fixture(scope="module")
def tree():
    return P.parse_tree(fixture("cnstrc_groups_full.json"))


# ---- refs ---------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("42442493", "42442493"),
    ("P_42442493", "42442493"),
    ("s314853", "S314853"),
    ("P_S175746", "S175746"),
    ("https://www.kmart.com.au/product/madison-mega-towel-ocean-42442493/", "42442493"),
    ("https://kmart.com.au/product/target-australian-cotton-classic-t-shirt-s314853/?x=1", "S314853"),
    ("//www.kmart.com.au/product/long-sleeve-terry-towel-set-s175746", "S175746"),
])
def test_resolve_product(value, expected):
    assert refs.resolve_product(value) == expected


@pytest.mark.parametrize("value", ["", "towel", "123", "https://example.com/product/x-42442493/",
                                   "https://www.kmart.com.au/category/toys/"])
def test_resolve_product_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_product(value)


@pytest.mark.parametrize("value,expected", [
    ("all", "all"),
    ("ALL", "all"),
    ("C86C082B7A671BE0B7B95B05AB10B8D1", "c86c082b7a671be0b7b95b05ab10b8d1"),
    ("https://www.kmart.com.au/category/home-and-living/bath-towels/", "url:/category/home-and-living/bath-towels/"),
    ("https://www.kmart.com.au/home-and-living", "url:/home-and-living/"),
    ("https://www.kmart.com.au/collection/wireless-headphones/", "collection:wireless-headphones"),
    ("/category/toys/", "url:/category/toys/"),
])
def test_resolve_category(value, expected):
    assert refs.resolve_category(value) == expected


@pytest.mark.parametrize("value", ["", "toys", "https://example.com/category/toys/", "https://www.kmart.com.au/"])
def test_resolve_category_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_category(value)


@pytest.mark.parametrize("value,expected", [
    ("abm-global", "abm-global"),
    ("ABM Global", "abm-global"),
    ("Bedding co.", "bedding-co."),
    ("Dave's Deals", "dave's-deals"),
    ("https://www.kmart.com.au/shop/target/", "target"),
    ("https://www.kmart.com.au/shop/Target?page=2", "target"),
])
def test_resolve_seller(value, expected):
    assert refs.resolve_seller(value) == expected


@pytest.mark.parametrize("value", ["", "https://example.com/shop/target/", "https://www.kmart.com.au/store-detail/x/", "-"])
def test_resolve_seller_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_seller(value)


@pytest.mark.parametrize("value,expected", [
    ("mandurah", "mandurah"),
    ("Mandurah", "mandurah"),
    ("1088", "id:1088"),
    ("https://www.kmart.com.au/store-detail/mandurah/", "mandurah"),
    ("https://kmart.com.au/store-detail/sydney-cbd", "sydney-cbd"),
])
def test_resolve_store(value, expected):
    assert refs.resolve_store(value) == expected


@pytest.mark.parametrize("value", ["", "https://example.com/store-detail/x/", "https://www.kmart.com.au/shop/x/", "a b"])
def test_resolve_store_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_store(value)


def test_sitemap_paths():
    assert refs.sitemap_path("products", "c") == "/sitemap/au/product-sitemap-c.xml"
    assert refs.sitemap_path("products") == "/sitemap/au/product-sitemap-a.xml"
    assert refs.sitemap_path("stores") == "/sitemap/au/storelocation-sitemap.xml"


# ---- value helpers --------------------------------------------------------------------

def test_value_helpers():
    assert P.number("9.00") == 9 and P.number("2.50") == 2.5 and P.number(None) is None
    assert P.to_float("WAS $11") == 11.0 and P.to_int("6") == 6 and P.to_int(True) is None
    assert P.iso_date("2026-09-30T18:42:09.000Z") == "2026-09-30"
    assert P.iso_date("9999-12-31") is None and P.iso_date("1899-12-30") is None and P.iso_date("") is None
    assert P.iso_datetime("2026-09-30T18:42:09.000Z") == "2026-09-30T18:42:09Z"
    assert P.to_bool("True") is True and P.to_bool("false") is False and P.to_bool("x") is None
    assert P.image_link("abc/42442370-2") == P.IMAGE_CDN + "abc/42442370-2" + P.IMAGE_SUFFIX
    assert P.image_link("https://x/y.jpg") == "https://x/y.jpg" and P.image_link("") is None
    assert P.parse_state_oos('{"NT": "6", "ACT": "6"}') == ["ACT", "NT"]
    assert P.parse_state_oos({"WA": "6", "ZZ": "6"}) == ["WA"]
    assert P.parse_state_oos(None) == [] and P.parse_state_oos("{") == []


def test_html_to_text():
    text = P.html_to_text("Soft towel.<br><br><strong>Product Details</strong><ul><li><strong>Size: </strong>1m</li>"
                          "<li>Cotton &amp; bamboo</li></ul>")
    assert text == "Soft towel.\nProduct Details\n- Size: 1m\n- Cotton & bamboo"
    assert P.html_to_text("") is None and P.html_to_text(None) is None


def test_pagination_caps_at_the_result_window():
    assert P.pagination(1, 40, 2143) == {"page": 1, "items_per_page": 40, "total_pages": 54, "total_count": 2143}
    assert P.pagination(3, 200, 150000)["total_pages"] == 50
    assert P.pagination(1, 40, 0) == {"page": 1, "items_per_page": 40, "total_pages": 0, "total_count": 0}
    assert P.pagination(1, 10, None)["total_count"] == 0


# ---- products -------------------------------------------------------------------------

def test_product_identity_and_links(towel):
    assert towel["id"] == "42442493"
    assert towel["name"] == "Madison Mega Towel - Ocean"
    assert towel["link"] == "https://www.kmart.com.au/product/madison-mega-towel-ocean-42442493/"
    assert towel["brand"] == "Anko"
    assert towel["image"].startswith("https://assets.kmart.com.au/transform/")
    assert len(towel["images"]) >= 2 and all(i.startswith("https://") for i in towel["images"])
    assert towel["rating"] == {"average": 4.6, "count": 348}
    assert towel["barcode"] and towel["barcode"].isdigit()
    assert towel["colour"] == "Blue" and towel["secondary_colour"] == "Ocean"


def test_product_description_and_pricing(towel):
    assert towel["description"].startswith("Dry yourself")
    assert "- " in towel["description"]          # the Product Details list
    assert towel["description_html"].startswith("Dry yourself") and "<ul>" in towel["description_html"]
    pricing = towel["pricing"]
    assert pricing["currency"] == "AUD"
    assert pricing["price"] == pricing["list_price"]
    assert pricing["was_price"] is None and pricing["is_on_sale"] is False
    assert pricing["promotion"] is None                 # only a list price on this one


def test_pricing_promotion_window():
    first = fixture("cnstrc_search_towel_p1.json")["response"]["results"][0]["data"]
    pricing = P.parse_pricing(first, today="2026-10-28")
    assert pricing["price"] == 2.5 and pricing["list_price"] == 2.5
    assert pricing["promotion"] == {"price": 2.5, "starts": "2026-05-14", "ends": "2026-06-03", "is_active": False}
    assert P.parse_pricing(first, today="2026-05-20")["promotion"]["is_active"] is True
    assert P.parse_pricing({"price": 8, "SavePrice": "WAS $11"}) == {
        "price": 8, "currency": "AUD", "list_price": None, "was_price": 11, "is_on_sale": True, "promotion": None}
    assert P.parse_pricing({})["price"] is None


def test_product_seller_and_shipping(towel, target_tee):
    assert towel["seller"] == {"id": 1, "name": "Kmart"}
    assert towel["sold_by"] == ["Kmart"]
    assert towel["is_marketplace"] is False
    assert towel["shipping"]["is_free"] is True and towel["shipping"]["fulfilment_channel"] == 3
    assert towel["pre_order"] == {"is_active": False, "release_date": None}
    assert towel["out_of_stock_states"] == []
    assert towel["category_id"] and len(towel["category_ids"]) > 3
    assert towel["merchandise"]["department"] is not None
    assert target_tee["seller"] == {"id": 2000, "name": "Target"}
    assert target_tee["id"] == "S314853"
    assert target_tee["description"].startswith("This product is not available")
    offer = target_tee["offers"][0]
    assert offer["seller"] == {"id": 2000, "name": "Target"}
    assert offer["price"] == 9 and offer["stock_quantity"] == 37
    assert offer["is_cheapest"] is True and offer["is_onepass_eligible"] is True
    assert "Australian cotton" in target_tee["badges"]


def test_product_variants_and_clearance(terry_set, target_tee):
    assert terry_set["id"] == "S175746"
    assert terry_set["variant_count"] == 12 and len(terry_set["variants"]) == 12
    assert terry_set["pricing"]["was_price"] == 14 and terry_set["pricing"]["is_on_sale"] is True
    assert terry_set["badges"] == ["Clearance"]
    assert terry_set["out_of_stock_states"] == ["ACT", "NT", "TAS"]
    variant = terry_set["variants"][0]
    assert variant["id"] and variant["size"] and variant["colour"] == "Pink"
    assert variant["pricing"]["price"] == 5 and variant["is_clearance"] is True
    assert variant["barcode"].isdigit() and variant["images"]
    assert len(target_tee["variants"]) == 59
    assert {v["is_default"] for v in target_tee["variants"]} <= {True, False}


def test_product_compact(items):
    compact = P.parse_product(items[2], compact=True)
    assert "description" not in compact and "offers" not in compact
    assert compact["variant_count"] == 59
    row = compact["variants"][0]
    assert set(row) == {"id", "colour", "size", "barcode", "image", "price", "is_default", "is_clearance",
                        "out_of_stock_states"}


def test_product_never_crashes_on_sparse_record():
    record = P.parse_product({"value": "x", "data": {"id": "P_1"}})
    assert record["id"] == "1" and record["link"] == "https://www.kmart.com.au/product/1/"
    assert record["pricing"]["price"] is None and record["variants"] == [] and record["seller"] is None
    assert record["rating"] == {"average": None, "count": None}
    assert P.parse_product({})["id"] is None
    assert P.parse_product(None)["name"] is None


# ---- listings -------------------------------------------------------------------------

def test_search_listing():
    listing = P.parse_listing(fixture("cnstrc_search_towel_p1.json"), 1, 40)
    assert len(listing["results"]) == 40
    assert listing["pagination"] == {"page": 1, "items_per_page": 40, "total_pages": 54, "total_count": 2143}
    assert listing["match_sources"] == {"keyword": 2143, "semantic": 0}
    assert listing["category"]["id"] == "all" and listing["category"]["children"][0]["name"] == "Home & Living"
    assert listing["category"]["children"][0]["link"] == "https://www.kmart.com.au/home-and-living/"
    names = [f["name"] for f in listing["facets"]]
    assert "Brand" in names and "Price" in names and "clearance" in names
    assert "__cnstrc_age" not in names and "stateOOS" not in names and "Available in NSW" not in names
    assert set(listing["availability_by_state"]) == set(refs.AU_STATES)
    assert listing["availability_by_state"]["NSW"] == {"available": 1634, "unavailable": 510}
    price = next(f for f in listing["facets"] if f["name"] == "Price")
    assert price["options"][0]["range"] == [None, 5] and price["options"][0]["label"] == "$5 and less"
    assert [s["value"] for s in listing["sort_options"]] == ["popular", "new", "price_asc", "price_desc"]
    assert listing["sort_options"][0]["is_selected"] is True
    first = listing["results"][0]
    assert first["id"] == "42442370" and first["pricing"]["price"] == 2.5


def test_filtered_sorted_search():
    listing = P.parse_listing(fixture("cnstrc_search_towel_filtered.json"), 1, 5)
    prices = [r["pricing"]["price"] for r in listing["results"]]
    assert prices == sorted(prices) and max(prices) <= 10
    assert listing["pagination"]["total_count"] == 32
    assert listing["sort_options"][2]["is_selected"] is True   # price_asc
    colour = next(f for f in listing["facets"] if f["name"] == "Colour")
    assert any(o["is_selected"] for o in colour["options"])


def test_nomatch_search_is_a_semantic_fallback():
    listing = P.parse_listing(fixture("cnstrc_search_nomatch.json"), 1, 3)
    assert listing["match_sources"] == {"keyword": 0, "semantic": 100}
    assert len(listing["results"]) == 3 and listing["pagination"]["total_count"] == 100
    assert P.listing_is_empty(fixture("cnstrc_search_nomatch.json")) is False


@pytest.mark.parametrize("name,expected_total", [
    ("cnstrc_browse_group_bath_towels_p1.json", 789),
    ("cnstrc_browse_collection_wireless_headphones.json", None),
    ("cnstrc_browse_brand_anko_p1.json", None),
    ("cnstrc_browse_shop_target_p1.json", None),
    ("cnstrc_browse_clearance_p1.json", None),
])
def test_browse_listings(name, expected_total):
    payload = fixture(name)
    listing = P.parse_listing(payload, 1, 10)
    assert listing["results"] and listing["pagination"]["total_count"] > 0
    if expected_total:
        assert listing["pagination"]["total_count"] == expected_total
    assert P.listing_is_empty(payload) is False
    for row in listing["results"]:
        assert row["id"] and row["name"] and row["link"].startswith("https://www.kmart.com.au/product/")


def test_group_listing_carries_the_current_category():
    listing = P.parse_listing(fixture("cnstrc_browse_group_bath_towels_p1.json"), 1, 40)
    assert listing["category"]["name"] == "Bath Towels"
    assert listing["category"]["path"] == ["Home & Living", "Bathroom", "Towels"]
    assert listing["category"]["link"] == "https://www.kmart.com.au/category/home-and-living/bath-towels/"


def test_clearance_listing_is_all_clearance():
    listing = P.parse_listing(fixture("cnstrc_browse_clearance_p1.json"), 1, 10)
    assert all(r["is_clearance"] for r in listing["results"])


def test_shop_listing_is_all_target():
    listing = P.parse_listing(fixture("cnstrc_browse_shop_target_p1.json"), 1, 10)
    assert all(r["seller"]["name"] == "Target" for r in listing["results"])


@pytest.mark.parametrize("name", ["cnstrc_browse_group_unknown.json", "cnstrc_browse_brand_unknown.json",
                                  "cnstrc_items_missing.json"])
def test_unknown_browse_is_empty(name):
    payload = fixture(name)
    assert P.listing_is_empty(payload) is True
    listing = P.parse_listing(payload, 1, 5)
    assert listing["results"] == [] and listing["pagination"]["total_count"] == 0 and listing["category"] is None


def test_unknown_collection_is_a_404_body():
    assert fixture("cnstrc_browse_collection_unknown.json") == {"message": "collection with ID nosuch-xyz not found"}


def test_listing_never_crashes_on_garbage():
    assert P.parse_listing({}, 1, 10)["results"] == []
    assert P.parse_listing(None, 2, 10)["pagination"]["page"] == 2
    assert P.parse_facets(None) == ([], {})
    assert P.listing_is_empty({}) is True


# ---- category tree --------------------------------------------------------------------

def test_category_tree(tree):
    assert tree["group_id"] == "all" and tree["count"] == 212459
    by_id, by_path = P.index_tree(tree)
    assert len(by_id) == 3352 and len(by_path) > 2000
    assert by_path["/category/home-and-living/bath-towels/"] == "c86c082b7a671be0b7b95b05ab10b8d1"
    assert by_path["/home-and-living/"] == "dddaa894234df841cfb678463562e055"
    node = P.parse_category_tree(by_id["dddaa894234df841cfb678463562e055"], 1)
    assert node["name"] == "Home & Living" and node["path"] == [] and node["children_count"] > 5
    assert node["children"][0]["children"] is None     # depth 1 stops there
    assert node["children"][0]["children_count"] >= 0
    leaf = P.parse_category_tree(by_id["c86c082b7a671be0b7b95b05ab10b8d1"], 2)
    assert leaf["product_count"] == 789 and leaf["children"] == [] and leaf["is_special"] is False
    assert leaf["path"] == ["Home & Living", "Bathroom", "Towels"]


def test_category_tree_special_flag(tree):
    specials = [n for n, _ in P.walk_tree(tree) if (n.get("data") or {}).get("isSpecial")]
    assert specials and P.parse_group(specials[0])["is_special"] is True


def test_tree_helpers_on_empty():
    assert P.parse_tree({}) is None
    assert P.index_tree({}) == ({}, {})
    assert P.parse_category_tree({}, 1)["id"] is None


# ---- autocomplete / recommendations ------------------------------------------------------

def test_autocomplete():
    out = P.parse_autocomplete(fixture("cnstrc_autocomplete_tow.json"))
    assert out["suggestions"][0]["term"] == "towel" and out["suggestions"][0]["product_count"] == 2110
    assert out["suggestions"][0]["categories"][0]["id"]
    assert len(out["suggestions"]) == 10 and len(out["products"]) == 6
    assert out["products"][0]["id"] and out["products"][0]["pricing"]["price"] is not None


def test_autocomplete_nomatch():
    out = P.parse_autocomplete(fixture("cnstrc_autocomplete_nomatch.json"))
    assert isinstance(out["suggestions"], list) and isinstance(out["products"], list)
    assert P.parse_autocomplete({}) == {"suggestions": [], "products": []}


def test_bestsellers():
    out = P.parse_recommendations(fixture("cnstrc_bestsellers.json"))
    assert out["pod"] == {"id": "bestsellers_products", "name": "Best Sellers"}
    assert out["count"] == 10 and len(out["results"]) == 10
    group = P.parse_recommendations(fixture("cnstrc_bestsellers_group.json"))
    assert len(group["results"]) == 5
    assert all("c86c082b7a671be0b7b95b05ab10b8d1" in r["category_ids"] for r in group["results"])
    assert P.parse_recommendations({})["results"] == []


# ---- reviews --------------------------------------------------------------------------

def test_reviews_page():
    out = P.parse_reviews(fixture("yotpo_reviews_42442493_p1.json"), 1, 5)
    assert out["product"] == {"id": "42442493", "name": "Madison Mega Towel - Ocean",
                              "image": out["product"]["image"]}
    assert out["summary"]["average"] == 4.62069 and out["summary"]["count"] == 348
    assert out["summary"]["star_distribution"] == {"1": 6, "2": 3, "3": 18, "4": 63, "5": 258}
    assert out["summary"]["ratings_breakdown"] == {"Value": 5, "Quality": 4}
    assert out["pagination"] == {"page": 1, "items_per_page": 5, "total_pages": 70, "total_count": 348}
    review = out["reviews"][0]
    assert review["id"] == 898272817 and review["rating"] == 5
    assert review["date"] == "2026-09-30T18:42:09Z"
    assert review["author"] == {"id": 323182843, "name": "Sarah W."}
    assert review["is_verified_buyer"] is True and review["votes"] == {"up": 0, "down": 0}
    assert review["ratings_breakdown"] == {"Value": 5, "Quality": 4}
    assert review["images"] == [] and review["reply"] is None


def test_reviews_star_filter():
    payload = fixture("yotpo_reviews_42442493_star5_images.json")
    out = P.parse_reviews(payload, 1, 3, star=5)
    assert all(r["rating"] == 5 for r in out["reviews"])
    assert out["pagination"]["total_count"] == 258     # from star_distribution, not Yotpo's unfiltered total
    assert P.parse_reviews(payload, 1, 3)["pagination"]["total_count"] == 348


def test_reviews_unknown_product():
    payload = fixture("yotpo_reviews_unknown.json")
    assert P.reviews_product_missing(payload) is True
    out = P.parse_reviews(payload, 1, 5)
    assert out["product"] is None and out["reviews"] == [] and out["summary"]["count"] == 0
    assert out["summary"]["star_distribution"] is None
    assert P.reviews_product_missing({}) is True
    assert P.parse_review({})["id"] is None


# ---- store / shop pages ---------------------------------------------------------------

def test_store_page():
    store = P.parse_store_page(fixture("store_mandurah.html"))
    assert store["id"] == 1088 and store["name"] == "Mandurah" and store["slug"] == "mandurah"
    assert store["link"] == "https://www.kmart.com.au/store-detail/mandurah/"
    assert store["phone"] == "+61 8 9534 0200"
    assert store["address"] == {"lines": ["Cnr Of Pinjarra And Mandurah Rd Mandurah"], "suburb": "Mandurah",
                                "state": "WA", "postcode": "6210", "country": "AU"}
    assert store["location"] == {"latitude": -32.535689, "longitude": 115.743117}
    assert len(store["trading_hours"]) == 7
    assert store["trading_hours"][0] == {"day": "Wednesday", "hours": "8:00AM - 9:00PM", "opens": "08:00",
                                         "closes": "21:00", "is_closed": False}
    sunday = next(h for h in store["trading_hours"] if h["day"] == "Sunday")
    assert sunday["opens"] == "10:00" and sunday["closes"] == "17:00"
    assert store["map_image"].startswith("https://maps.googleapis.com/")


def test_trading_hours_closed_and_garbage():
    rows = P.parse_trading_hours([{"weekDay": "SUNDAY", "hours": "Closed"}, {}, None])
    assert rows[0] == {"day": "Sunday", "hours": "Closed", "opens": None, "closes": None, "is_closed": True}
    assert rows[1]["day"] is None and rows[2]["hours"] is None


def test_store_404_page_is_not_a_store():
    assert P.parse_store_page(fixture("store_unknown_404.html")) is None
    assert P.parse_store_page("") is None and P.parse_store_page(None) is None
    assert P.next_data("<html></html>") is None


def test_shop_pages():
    target = P.parse_shop_page(fixture("shop_target.html"))
    assert target["id"] == 2000 and target["name"] == "Target" and target["slug"] == "target"
    assert target["link"] == "https://www.kmart.com.au/shop/target/"
    assert target["logo"].startswith("https://kmartau-prod.mirakl.net/")
    assert target["description"].startswith("Target Australia")
    assert target["shipping_policy"].startswith("Once your payment")
    assert target["product_count"] > 1000 and target["categories"] and target["categories"][0]["id"]
    assert target["is_onepass_shop"] is True and target["is_marketplace_shop"] is False
    assert target["has_product_listing"] is True and target["has_storefront"] is False
    abm = P.parse_shop_page(fixture("shop_abm_global.html"))
    assert abm["id"] == 2039 and abm["slug"] == "abm-global" and abm["product_count"] > 0


def test_shop_404_page_is_not_a_shop():
    assert P.parse_shop_page(fixture("shop_unknown_404.html")) is None
    assert P.parse_shop_page("<html></html>") is None


# ---- sellers index ---------------------------------------------------------------------

def test_seller_index():
    rows = P.parse_seller_index(fixture("cnstrc_browse_all_facets.json"),
                                P.parse_sitemap_urls(fixture("sitemap_seller.xml")))
    by_slug = {r["slug"]: r for r in rows}
    assert len(rows) >= 150
    assert by_slug["target"]["name"] == "Target" and by_slug["target"]["has_shop_page"] is True
    assert by_slug["target"]["link"] == "https://www.kmart.com.au/shop/target/"
    assert by_slug["target"]["product_count"] > 10000 and by_slug["target"]["page_updated"] == "2026-10-01"
    assert by_slug["kmart"]["has_shop_page"] is False and by_slug["kmart"]["link"] is None
    assert by_slug["bedding-co."]["name"] == "Bedding co."
    assert rows[0]["product_count"] >= rows[1]["product_count"]
    assert P.parse_seller_index({}, []) == []


# ---- sitemaps -------------------------------------------------------------------------

def test_sitemap_index():
    rows = P.parse_sitemap_index(fixture("sitemap_index.xml"))
    assert len(rows) == 14
    assert rows[0] == {"type": "categories", "part": None,
                       "link": "https://www.kmart.com.au/sitemap/au/category-sitemap.xml", "last_modified": "2026-10-28"}
    products = [r for r in rows if r["type"] == "products"]
    assert [r["part"] for r in products] == list("abcdefghi")
    assert P.parse_sitemap_index("") == []


def test_product_sitemap():
    rows = P.parse_sitemap_urls(fixture("sitemap_product_i_head300.xml"))
    assert len(rows) == 300
    assert rows[0] == {"link": "https://www.kmart.com.au/product/advwin-high-bay-lights-6500k-21000lm-10-pack-ip65-waterproof-black-110089106/",
                       "id": "110089106", "slug": "advwin-high-bay-lights-6500k-21000lm-10-pack-ip65-waterproof-black",
                       "last_modified": "2026-10-01", "change_frequency": "weekly", "priority": 0.7}
    assert all(r["id"] for r in rows)


def test_other_sitemaps():
    stores = P.parse_sitemap_urls(fixture("sitemap_storelocation.xml"))
    assert len(stores) > 300 and stores[0]["slug"] == "mandurah"
    sellers = P.parse_sitemap_urls(fixture("sitemap_seller.xml"))
    assert sellers[0]["slug"] == "target" and len(sellers) > 100
    collections = P.parse_sitemap_urls(fixture("sitemap_collection.xml"))
    assert collections and all(r["slug"] for r in collections)
    categories = P.parse_sitemap_urls(fixture("sitemap_category_head300.xml"))
    assert categories[0]["path"] == "/category/home-and-living/10-and-under/"
    content = P.parse_sitemap_urls(fixture("sitemap_content.xml"))
    assert content[0]["link"] == "https://www.kmart.com.au" and "id" not in content[0]
    assert P.parse_sitemap_urls("") == [] and P.parse_sitemap_urls(None) == []


# ---- store ranking ----------------------------------------------------------------------

@pytest.fixture(scope="module")
def stores():
    mandurah = P.parse_store_page(fixture("store_mandurah.html"))
    sydney = dict(mandurah, id=1, name="Sydney CBD", slug="sydney-cbd",
                  address={"lines": ["500 George St"], "suburb": "Sydney", "state": "NSW", "postcode": "2000", "country": "AU"},
                  location={"latitude": -33.8688, "longitude": 151.2093})
    return [mandurah, sydney]


def test_parse_location_query():
    assert P.parse_location_query("-32.5, 115.7") == ("coords", (-32.5, 115.7))
    assert P.parse_location_query("6210") == ("postcode", "6210")
    assert P.parse_location_query("  Mandurah  WA ") == ("text", "mandurah wa")


def test_rank_stores(stores):
    by_coords = P.rank_stores(stores, "-33.87,151.21")
    assert [s["name"] for s in by_coords] == ["Sydney CBD", "Mandurah"] and by_coords[0]["distance_km"] < 1
    assert [s["name"] for s in P.rank_stores(stores, "6214")] == ["Mandurah"]
    assert P.rank_stores(stores, "9999") == []
    assert [s["name"] for s in P.rank_stores(stores, "mandurah")] == ["Mandurah"]
    assert [s["name"] for s in P.rank_stores(stores, "george st")] == ["Sydney CBD"]
    assert P.rank_stores(stores, "nowhere") == []
    assert [s["name"] for s in P.rank_stores(stores, None, "NSW")] == ["Sydney CBD"]
    assert [s["name"] for s in P.rank_stores(stores)] == ["Sydney CBD", "Mandurah"]   # by state, then name
    assert "distance_km" not in P.rank_stores(stores)[0]
    assert P.rank_stores([], "2000") == [] and P.rank_stores(None) == []
