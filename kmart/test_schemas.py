"""Offline tests for the /kmart/* request schemas.

    python -m pytest kmart/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kmart import schemas  # noqa: E402

LISTING_DEFAULTS = {"brand": None, "colour": None, "size": None, "seller": None, "min_price": None,
                    "max_price": None, "state": None, "clearance": None, "online_only": None, "onepass": None,
                    "sort": "popular", "page": 1, "limit": 40}


def errors(schema, data):
    with pytest.raises(ValidationError) as info:
        schema().load(data)
    return info.value.normalized_messages()


# ---- products -------------------------------------------------------------------------

def test_product_schema_accepts_keycode_and_link():
    assert schemas.ProductSchema().load({"product": "42442493"}) == {"product": "42442493"}
    assert schemas.ProductSchema().load({"product": "p_s314853"}) == {"product": "S314853"}
    assert schemas.ProductSchema().load(
        {"product": "https://www.kmart.com.au/product/madison-mega-towel-ocean-42442493/"}) == {"product": "42442493"}


def test_product_schema_rejects():
    assert "keycode" in errors(schemas.ProductSchema, {"product": "towel"})["product"][0]
    assert "kmart.com.au" in errors(schemas.ProductSchema, {"product": "https://example.com/product/x-42442493/"})["product"][0]
    assert "product" in errors(schemas.ProductSchema, {})
    assert "url" in errors(schemas.ProductSchema, {"product": "42442493", "url": "x"})   # no sibling params


def test_products_bulk_schema():
    loaded = schemas.ProductsBulkSchema().load(
        {"products": "42442493, S314853,https://www.kmart.com.au/product/x-42442370/,42442493"})
    assert loaded == {"products": ["42442493", "S314853", "42442370"]}
    assert "'towel'" in errors(schemas.ProductsBulkSchema, {"products": "42442493,towel"})["products"][0]
    assert "at least one" in errors(schemas.ProductsBulkSchema, {"products": " , "})["products"][0]
    too_many = ",".join(str(40000000 + i) for i in range(101))
    assert "At most 100" in errors(schemas.ProductsBulkSchema, {"products": too_many})["products"][0]


def test_search_schema_defaults_and_filters():
    loaded = schemas.ProductsSearchSchema().load({"query": " towel "})
    assert loaded == {"query": "towel", "category": None, **LISTING_DEFAULTS}
    loaded = schemas.ProductsSearchSchema().load({
        "query": "towel", "brand": "Anko", "colour": "Blue", "min_price": "2", "max_price": "10.5",
        "state": "nsw", "clearance": "true", "online_only": "0", "sort": "PRICE_ASC", "page": "3", "limit": "200",
        "seller": "ABM Global", "category": "https://www.kmart.com.au/home-and-living/"})
    assert loaded["state"] == "nsw" and loaded["clearance"] is True and loaded["online_only"] is False
    assert loaded["sort"] == "price_asc" and loaded["page"] == 3 and loaded["limit"] == 200
    assert loaded["min_price"] == 2.0 and loaded["max_price"] == 10.5
    assert loaded["seller"] == "abm-global" and loaded["category"] == "url:/home-and-living/"


def test_search_schema_rejects():
    assert "query" in errors(schemas.ProductsSearchSchema, {})
    assert "limit" in errors(schemas.ProductsSearchSchema, {"query": "x", "limit": "201"})
    assert "page" in errors(schemas.ProductsSearchSchema, {"query": "x", "page": "0"})
    assert "sort" in errors(schemas.ProductsSearchSchema, {"query": "x", "sort": "cheapest"})
    assert "state" in errors(schemas.ProductsSearchSchema, {"query": "x", "state": "ny"})
    assert "clearance" in errors(schemas.ProductsSearchSchema, {"query": "x", "clearance": "maybe"})
    assert "max_price" in errors(schemas.ProductsSearchSchema, {"query": "x", "min_price": "10", "max_price": "5"})
    assert "min_price" in errors(schemas.ProductsSearchSchema, {"query": "x", "min_price": "-1"})
    assert "category" in errors(schemas.ProductsSearchSchema, {"query": "x", "category": "toys"})
    assert "foo" in errors(schemas.ProductsSearchSchema, {"query": "x", "foo": "bar"})


def test_reviews_schema():
    loaded = schemas.ProductReviewsSchema().load({"product": "42442493"})
    assert loaded == {"product": "42442493", "sort": "newest", "rating": None, "page": 1, "limit": 10}
    loaded = schemas.ProductReviewsSchema().load({"product": "42442493", "sort": "Helpful", "rating": "5", "limit": "150"})
    assert loaded["sort"] == "helpful" and loaded["rating"] == 5 and loaded["limit"] == 150
    assert "rating" in errors(schemas.ProductReviewsSchema, {"product": "42442493", "rating": "6"})
    assert "limit" in errors(schemas.ProductReviewsSchema, {"product": "42442493", "limit": "151"})
    assert "sort" in errors(schemas.ProductReviewsSchema, {"product": "42442493", "sort": "random"})


def test_suggestions_and_bestsellers_schemas():
    assert schemas.ProductsSuggestionsSchema().load({"query": "tow"}) == {"query": "tow", "limit": 8}
    assert "limit" in errors(schemas.ProductsSuggestionsSchema, {"query": "tow", "limit": "21"})
    assert "query" in errors(schemas.ProductsSuggestionsSchema, {"query": ""})
    assert schemas.ProductsBestsellersSchema().load({}) == {"category": None, "limit": 20}
    loaded = schemas.ProductsBestsellersSchema().load({"category": "c86c082b7a671be0b7b95b05ab10b8d1", "limit": "100"})
    assert loaded["category"] == "c86c082b7a671be0b7b95b05ab10b8d1" and loaded["limit"] == 100
    assert "limit" in errors(schemas.ProductsBestsellersSchema, {"limit": "101"})


# ---- categories / specials ----------------------------------------------------------------

def test_categories_schema():
    assert schemas.CategoriesSchema().load({}) == {"category": "all", "depth": 2}
    loaded = schemas.CategoriesSchema().load({"category": "https://www.kmart.com.au/category/toys/", "depth": "6"})
    assert loaded == {"category": "url:/category/toys/", "depth": 6}
    assert "depth" in errors(schemas.CategoriesSchema, {"depth": "7"})
    assert "depth" in errors(schemas.CategoriesSchema, {"depth": "0"})
    assert "category" in errors(schemas.CategoriesSchema, {"category": "toys"})


def test_category_products_schema():
    loaded = schemas.CategoryProductsSchema().load({"category": "https://www.kmart.com.au/collection/wireless-headphones/"})
    assert loaded == {"category": "collection:wireless-headphones", **LISTING_DEFAULTS}
    assert "category" in errors(schemas.CategoryProductsSchema, {})
    assert "category" in errors(schemas.CategoryProductsSchema, {"category": "https://example.com/toys/"})


def test_specials_schema():
    loaded = schemas.SpecialsSchema().load({"type": "Clearance"})
    assert loaded == {"type": "clearance", "category": None, **LISTING_DEFAULTS}
    assert "type" in errors(schemas.SpecialsSchema, {})
    assert "one of" in errors(schemas.SpecialsSchema, {"type": "sale"})["type"][0]


# ---- brands / sellers ------------------------------------------------------------------

def test_brands_schemas():
    assert schemas.BrandsSchema().load({}) == {"category": None, "query": None}
    assert schemas.BrandsSchema().load({"query": " le "}) == {"category": None, "query": "le"}
    loaded = schemas.BrandProductsSchema().load({"brand": "Anko"})
    assert loaded == {**LISTING_DEFAULTS, "brand": "Anko"}
    assert "brand" in errors(schemas.BrandProductsSchema, {})
    assert "brand" in errors(schemas.BrandProductsSchema, {"brand": ""})


def test_sellers_schemas():
    assert schemas.SellersSchema().load({}) == {"query": None}
    assert schemas.SellerSchema().load({"seller": "ABM Global"}) == {"seller": "abm-global"}
    assert schemas.SellerSchema().load({"seller": "https://www.kmart.com.au/shop/target/"}) == {"seller": "target"}
    assert "seller" in errors(schemas.SellerSchema, {})
    assert "kmart.com.au" in errors(schemas.SellerSchema, {"seller": "https://example.com/shop/target/"})["seller"][0]
    loaded = schemas.SellerProductsSchema().load({"seller": "target", "sort": "new"})
    assert loaded["seller"] == "target" and loaded["sort"] == "new"
    assert "seller" in errors(schemas.SellerProductsSchema, {"sort": "new"})


# ---- stores -------------------------------------------------------------------------------

def test_stores_schemas():
    assert schemas.StoresSearchSchema().load({}) == {"location": None, "state": None, "page": 1, "limit": 20}
    loaded = schemas.StoresSearchSchema().load({"location": "-32.5,115.7", "state": "wa", "limit": "100"})
    assert loaded == {"location": "-32.5,115.7", "state": "wa", "page": 1, "limit": 100}
    assert "limit" in errors(schemas.StoresSearchSchema, {"limit": "101"})
    assert "state" in errors(schemas.StoresSearchSchema, {"state": "NY"})
    assert schemas.StoreSchema().load({"store": "1088"}) == {"store": "id:1088"}
    assert schemas.StoreSchema().load({"store": "Mandurah"}) == {"store": "mandurah"}
    assert "store" in errors(schemas.StoreSchema, {})
    assert "store" in errors(schemas.StoreSchema, {"store": "https://example.com/store-detail/x/"})


# ---- sitemaps -----------------------------------------------------------------------------

def test_sitemap_schemas():
    assert schemas.SitemapIndexSchema().load({}) == {}
    assert "x" in errors(schemas.SitemapIndexSchema, {"x": "1"})
    assert schemas.SitemapLinksSchema().load({"type": "Products"}) == {"type": "products", "part": None, "page": 1, "limit": 100}
    loaded = schemas.SitemapLinksSchema().load({"type": "products", "part": "C", "page": "2", "limit": "1000"})
    assert loaded == {"type": "products", "part": "c", "page": 2, "limit": 1000}
    assert "type" in errors(schemas.SitemapLinksSchema, {})
    assert "type" in errors(schemas.SitemapLinksSchema, {"type": "images"})
    assert "part" in errors(schemas.SitemapLinksSchema, {"type": "products", "part": "z"})
    assert "part" in errors(schemas.SitemapLinksSchema, {"type": "stores", "part": "a"})
    assert "limit" in errors(schemas.SitemapLinksSchema, {"type": "stores", "limit": "1001"})
