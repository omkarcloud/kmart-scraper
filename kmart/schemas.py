"""Marshmallow request schemas for every /kmart/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    product    42442493 | S314853 | kmart.com.au/product/madison-mega-towel-ocean-42442493/
    products   up to 100 of the above, comma-separated
    category   c86c082b7a671be0b7b95b05ab10b8d1 | all | kmart.com.au/category/home-and-living/bath-towels/
               | kmart.com.au/collection/wireless-headphones/
    seller     abm-global | ABM Global | kmart.com.au/shop/abm-global/
    store      mandurah | 1088 | kmart.com.au/store-detail/mandurah/
    brand      Anko (a "Brand" facet value, see /kmart/brands)
    location   Mandurah | 6210 | -32.5357,115.7431

Listing routes (search, category / brand / seller products, specials) share
the same filter set, which maps onto Constructor's facets (kmart/api.py):
brand, colour, size, seller, min_price / max_price, state (in stock in that
state), clearance, online_only, onepass, sort, page, limit (<= 200, the
engine's page cap).
"""
from marshmallow import ValidationError, fields, missing, validate

from kmart import refs
from kmart.fetch import MAX_ITEM_IDS, MAX_PAGE_SIZE, MAX_RECOMMENDATIONS, MAX_REVIEWS_PER_PAGE
from kmart.parsers import RESULT_WINDOW, SORTS
from schema_fields import (BaseSchema, ChoiceField, Flag, LimitField, PageField, PageSizeField,
                           PositiveInt, Price, QueryField, RefField, StrippedString)

DEFAULT_PAGE_SIZE = 40            # the site's own listing page
MAX_LISTING_PAGE = RESULT_WINDOW // 20   # 500: past the 10,000th result Constructor serves nothing

REVIEW_SORTS = {
    "newest": ("date", "desc"),
    "oldest": ("date", "asc"),
    "helpful": ("votes_up", "desc"),
    "highest": ("rating", "desc"),
    "lowest": ("rating", "asc"),
    "images": ("images", "desc"),
}

SPECIAL_TYPES = ("clearance", "online_only", "onepass", "new")


class ProductRefField(RefField):
    """`product`: a keycode or product link -> the keycode."""
    resolver = staticmethod(refs.resolve_product)


class CategoryRefField(RefField):
    """`category`: a group id, "all", or a category / collection link."""
    resolver = staticmethod(refs.resolve_category)


class SellerRefField(RefField):
    """`seller`: a shop slug, name or /shop/ link -> the slug."""
    resolver = staticmethod(refs.resolve_seller)


class StoreRefField(RefField):
    """`store`: a store slug, number or /store-detail/ link."""
    resolver = staticmethod(refs.resolve_store)


class ProductListField(fields.Field):
    """`products`: comma-separated keycodes / links -> deduped keycode list."""

    def __init__(self, max_items=MAX_ITEM_IDS, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)
        self.max_items = max_items

    def _deserialize(self, value, attr, data, **kwargs):
        items = []
        for raw in str(value or "").replace("\n", ",").split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                keycode = refs.resolve_product(raw)
            except ValueError as e:
                raise ValidationError(f"'{raw}': {e}")
            if keycode not in items:
                items.append(keycode)
        if not items:
            raise ValidationError("Pass at least one keycode (e.g. 42442493,S314853).")
        if len(items) > self.max_items:
            raise ValidationError(f"At most {self.max_items} products per request.")
        return items


# ---- shared listing filters ---------------------------------------------------------

class ListingSchema(BaseSchema):
    """Filters, sort and paging shared by every product listing route."""
    brand = StrippedString(required=False, load_default=None, validate=validate.Length(max=100),
                           metadata={"description": "brand name as the Brand facet lists it (Anko, Adidas)"})
    colour = StrippedString(required=False, load_default=None, validate=validate.Length(max=50),
                            metadata={"description": "colour facet value (Blue, Green, Multi)"})
    size = StrippedString(required=False, load_default=None, validate=validate.Length(max=50),
                          metadata={"description": "size facet value (M, 10, One Size)"})
    seller = SellerRefField(required=False, load_default=None,
                            metadata={"description": "only this seller: shop slug, name or /shop/ link (kmart, target, abm-global)"})
    min_price = Price(metadata={"description": "lowest price in AUD"})
    max_price = Price(metadata={"description": "highest price in AUD"})
    state = ChoiceField(list(refs.AU_STATES), metadata={
        "description": "only products in stock in this state (NSW, VIC, QLD, WA, SA, TAS, ACT, NT)"})
    clearance = Flag(metadata={"description": "true = clearance items only, false = exclude them"})
    online_only = Flag(metadata={"description": "true = online-only items, false = items also sold in store"})
    onepass = Flag(metadata={"description": "true = OnePass-eligible items only"})
    sort = ChoiceField(list(SORTS), load_default="popular",
                       metadata={"description": "popular (default), new, price_asc, price_desc"})
    page = PageField(max_page=MAX_LISTING_PAGE, metadata={"description": "1-based page"})
    limit = PageSizeField(default=DEFAULT_PAGE_SIZE, max_size=MAX_PAGE_SIZE,
                          metadata={"description": f"products per page, default {DEFAULT_PAGE_SIZE}, max {MAX_PAGE_SIZE}"})

    def _validate_prices(self, data):
        lo, hi = data.get("min_price"), data.get("max_price")
        if lo is not None and hi is not None and lo > hi:
            raise ValidationError("min_price must not exceed max_price.", "max_price")

    def load(self, *args, **kwargs):
        data = super().load(*args, **kwargs)
        self._validate_prices(data)
        return data


# ---- products -------------------------------------------------------------------------

class ProductsSearchSchema(ListingSchema):
    query = QueryField(metadata={"description": "search term (towel, air fryer, lego)"})
    category = CategoryRefField(required=False, load_default=None, metadata={
        "description": "restrict to a category: group id, or a kmart.com.au category link"})


class ProductSchema(BaseSchema):
    product = ProductRefField(metadata={"description": "keycode (42442493, S314853) or a kmart.com.au product link"})


class ProductsBulkSchema(BaseSchema):
    products = ProductListField(metadata={"description": f"comma-separated keycodes or product links, up to {MAX_ITEM_IDS}"})


class ProductReviewsSchema(BaseSchema):
    product = ProductRefField(metadata={"description": "keycode or a kmart.com.au product link"})
    sort = ChoiceField(list(REVIEW_SORTS), load_default="newest",
                       metadata={"description": "newest (default), oldest, helpful, highest, lowest, images"})
    rating = PositiveInt(max_value=5, metadata={"description": "only reviews with this star rating (1-5)"})
    page = PageField(max_page=1000, metadata={"description": "1-based page"})
    limit = PageSizeField(default=10, max_size=MAX_REVIEWS_PER_PAGE,
                          metadata={"description": f"reviews per page, default 10, max {MAX_REVIEWS_PER_PAGE}"})


class ProductsSuggestionsSchema(BaseSchema):
    query = QueryField(max_length=100, metadata={"description": "partial search term (tow, air fr)"})
    limit = LimitField(default=8, max_size=20, metadata={"description": "product suggestions to return, default 8, max 20"})


class ProductsBestsellersSchema(BaseSchema):
    category = CategoryRefField(required=False, load_default=None, metadata={
        "description": "restrict to a category: group id, or a kmart.com.au category link"})
    limit = LimitField(default=20, max_size=MAX_RECOMMENDATIONS,
                       metadata={"description": f"products to return, default 20, max {MAX_RECOMMENDATIONS}"})


# ---- categories -----------------------------------------------------------------------

class CategoriesSchema(BaseSchema):
    category = CategoryRefField(required=False, load_default="all", metadata={
        "description": "root of the tree to return: group id, or a kmart.com.au category link (default: all)"})
    depth = PositiveInt(max_value=6, load_default=2, metadata={"description": "levels of children to include, default 2, max 6"})


class CategoryProductsSchema(ListingSchema):
    category = CategoryRefField(metadata={
        "description": "group id, or a kmart.com.au category or collection link"})


class SpecialsSchema(ListingSchema):
    type = ChoiceField(list(SPECIAL_TYPES), required=True, load_default=missing,
                       metadata={"description": "clearance, online_only, onepass or new (latest arrivals)"})
    category = CategoryRefField(required=False, load_default=None, metadata={
        "description": "restrict to a category: group id, or a kmart.com.au category link"})


# ---- brands ---------------------------------------------------------------------------

class BrandsSchema(BaseSchema):
    category = CategoryRefField(required=False, load_default=None, metadata={
        "description": "only brands with products in this category"})
    query = StrippedString(required=False, load_default=None, validate=validate.Length(max=100),
                           metadata={"description": "only brands whose name contains this text"})


class BrandProductsSchema(ListingSchema):
    brand = StrippedString(required=True, validate=validate.Length(min=1, max=100),
                           metadata={"description": "brand name as /kmart/brands lists it (Anko, LEGO)"})


# ---- sellers --------------------------------------------------------------------------

class SellersSchema(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=validate.Length(max=100),
                           metadata={"description": "only sellers whose name contains this text"})


class SellerSchema(BaseSchema):
    seller = SellerRefField(metadata={"description": "shop slug (abm-global), name (ABM Global) or a kmart.com.au /shop/ link"})


class SellerProductsSchema(ListingSchema):
    seller = SellerRefField(metadata={"description": "shop slug, name or a kmart.com.au /shop/ link"})


# ---- stores ---------------------------------------------------------------------------

class StoresSearchSchema(BaseSchema):
    location = StrippedString(required=False, load_default=None, validate=validate.Length(max=100),
                              metadata={"description": "suburb / store name, a 4-digit postcode, or lat,lng (-32.5357,115.7431); omit for every store"})
    state = ChoiceField(list(refs.AU_STATES), metadata={"description": "only stores in this state"})
    page = PageField(max_page=50, metadata={"description": "1-based page"})
    limit = PageSizeField(default=20, max_size=100, metadata={"description": "stores per page, default 20, max 100"})


class StoreSchema(BaseSchema):
    store = StoreRefField(metadata={"description": "store slug (mandurah), store number (1088) or a kmart.com.au /store-detail/ link"})


# ---- sitemaps -------------------------------------------------------------------------

class SitemapIndexSchema(BaseSchema):
    """No parameters."""


class SitemapLinksSchema(BaseSchema):
    type = ChoiceField(list(refs.SITEMAP_TYPES), required=True, load_default=missing,
                       metadata={"description": "products, categories, collections, sellers, stores or content"})
    part = ChoiceField(list(refs.SITEMAP_PRODUCT_PARTS),
                       metadata={"description": "products only: which product sitemap file, a-i (default a)"})
    page = PageField(max_page=1000, metadata={"description": "1-based page"})
    limit = PageSizeField(default=100, max_size=1000, metadata={"description": "links per page, default 100, max 1000"})

    def load(self, *args, **kwargs):
        data = super().load(*args, **kwargs)
        if data.get("part") and data.get("type") != "products":
            raise ValidationError("part applies to type=products only.", "part")
        return data
