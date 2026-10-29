"""Reference resolvers + site constants for /kmart/*.

ONE param per input (tripadvisor QueryOrIdField convention): every id-like
param accepts a bare id OR any kmart.com.au link, and the resolver returns
the canonical form the fetchers use. Resolvers raise ValueError with a
user-facing message (schema_fields.RefField turns it into a 400).

Identifier shapes on kmart.com.au (captured 2026-10-28):

  * product   the "keycode": 8 digits for Kmart's own range (42442493),
              "S" + digits for marketplace / Target / Officeworks listings
              (S314853). Product links end in the keycode:
              /product/madison-mega-towel-ocean-42442493/. Constructor.io
              indexes the item as P_<keycode>; Yotpo keys reviews on the
              bare keycode.
  * category  a 32-hex Constructor group id (c86c082b7a671be0b7b95b05ab10b8d1),
              "all" (the root), or a category link — top-level
              /home-and-living/, nested /category/home-and-living/bath-towels/,
              or a curated /collection/<slug>/ page (a Constructor
              collection, browsed by its slug). A link resolves to
              "url:<path>" / "collection:<slug>"; api.py maps a path to its
              group id through the cached category tree.
  * seller    a marketplace shop slug (abm-global), the shop's display
              name as the "Shops" facet lists it (ABM Global) or a
              /shop/<slug>/ link -> the slug (lower-cased, spaces to "-",
              which is how the seller sitemap spells "bedding-co." and
              "dave's-deals").
  * store     a store slug (mandurah), the numeric location id (1088) or a
              /store-detail/<slug>/ link -> the slug, or "id:<n>" for a
              numeric id (api.py maps it through the store index).
"""
import re
from urllib.parse import unquote, urlparse

SITE = "https://www.kmart.com.au"

KEYCODE_RE = re.compile(r"^(?:P_)?(S?\d{5,10})$", re.I)
_LINK_KEYCODE_RE = re.compile(r"/product/(?:[^/]*?-)?(S?\d{5,10})/?(?:[?#]|$)", re.I)
GROUP_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9.'&_-]*$")
_LINK_SHOP_RE = re.compile(r"/shop/([^/?#]+)")
_LINK_STORE_RE = re.compile(r"/store-detail/([^/?#]+)")
_LINK_COLLECTION_RE = re.compile(r"/collection/([^/?#]+)")

AU_STATES = ("NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT")


def _is_link(value):
    return value.startswith(("http://", "https://", "//"))


def _site_path(value, what):
    """A kmart.com.au link -> its path (ValueError for another site)."""
    url = value if not value.startswith("//") else "https:" + value
    host = (urlparse(url).hostname or "").lower()
    if not (host == "kmart.com.au" or host.endswith(".kmart.com.au")):
        raise ValueError(f"Must be a kmart.com.au {what} link.")
    return unquote(urlparse(url).path or "/")


# ---- products -----------------------------------------------------------------

def resolve_product(value):
    """Bare keycode (42442493 / S314853 / P_42442493) or a product link ->
    the canonical keycode (upper-case S prefix for marketplace items)."""
    value = (value or "").strip()
    match = KEYCODE_RE.match(value)
    if match:
        return match.group(1).upper()
    if _is_link(value):
        path = _site_path(value, "product")
        match = _LINK_KEYCODE_RE.search(path)
        if match:
            return match.group(1).upper()
        raise ValueError("Must be a kmart.com.au product link "
                         "(https://www.kmart.com.au/product/<name>-<keycode>/).")
    raise ValueError("Must be a Kmart keycode (42442493, S314853) or a kmart.com.au product link.")


def constructor_item_id(keycode):
    """The Constructor.io item id for a keycode."""
    return f"P_{keycode}"


def keycode_from_item_id(item_id):
    """P_42442493 -> 42442493 (anything else is returned as-is)."""
    item_id = str(item_id or "")
    return item_id[2:] if item_id.startswith("P_") else item_id


def product_link(path_or_keycode):
    """Absolute product link from Constructor's relative `url`, or a bare
    keycode when no path is known."""
    value = str(path_or_keycode or "")
    if value.startswith("/"):
        return SITE + value
    if value.startswith("http"):
        return value
    return f"{SITE}/product/{value}/" if value else None


# ---- categories ---------------------------------------------------------------

def resolve_category(value):
    """32-hex group id | "all" | a category / collection link ->
    the group id, "all", "url:<path>" or "collection:<slug>"."""
    value = (value or "").strip()
    low = value.lower()
    if low == "all":
        return "all"
    if GROUP_ID_RE.match(low):
        return low
    if _is_link(value):
        path = _site_path(value, "category")
        match = _LINK_COLLECTION_RE.search(path)
        if match:
            return "collection:" + match.group(1).lower()
        path = path.rstrip("/") + "/"
        if path == "/":
            raise ValueError("Must be a kmart.com.au category link "
                             "(https://www.kmart.com.au/category/<path>/).")
        return "url:" + path
    if low.startswith("/"):
        if _LINK_COLLECTION_RE.search(low):
            return "collection:" + _LINK_COLLECTION_RE.search(low).group(1)
        return "url:" + low.rstrip("/") + "/"
    raise ValueError("Must be a category id (32 hex characters), \"all\", or a "
                     "kmart.com.au category or collection link.")


# ---- sellers ------------------------------------------------------------------

def seller_slug(name):
    """A seller's display name -> its /shop/<slug>/ slug (the sitemap keeps
    punctuation: "Bedding co." -> bedding-co., "Dave's Deals" -> dave's-deals)."""
    return re.sub(r"\s+", "-", (name or "").strip().lower())


def resolve_seller(value):
    """Shop slug, the shop's display name, or a /shop/<slug>/ link -> the slug."""
    value = (value or "").strip()
    if _is_link(value):
        path = _site_path(value, "shop")
        match = _LINK_SHOP_RE.search(path)
        if match:
            return match.group(1).lower()
        raise ValueError("Must be a kmart.com.au shop link (https://www.kmart.com.au/shop/<slug>/).")
    slug = seller_slug(value)
    if not slug or not _SLUG_RE.match(slug):
        raise ValueError("Must be a seller slug (abm-global), a seller name (ABM Global) "
                         "or a kmart.com.au shop link.")
    return slug


def seller_link(slug):
    return f"{SITE}/shop/{slug}/"


# ---- stores -------------------------------------------------------------------

def resolve_store(value):
    """Store slug, numeric location id, or a /store-detail/<slug>/ link ->
    the slug, or "id:<n>" for a numeric id."""
    value = (value or "").strip()
    if value.isdigit():
        return "id:" + str(int(value))
    if _is_link(value):
        path = _site_path(value, "store")
        match = _LINK_STORE_RE.search(path)
        if match:
            return match.group(1).lower()
        raise ValueError("Must be a kmart.com.au store link "
                         "(https://www.kmart.com.au/store-detail/<slug>/).")
    slug = value.lower()
    if not _SLUG_RE.match(slug):
        raise ValueError("Must be a store slug (mandurah), a store number (1088) "
                         "or a kmart.com.au store link.")
    return slug


def store_link(slug):
    return f"{SITE}/store-detail/{slug}/"


def store_slug_from_link(link):
    match = _LINK_STORE_RE.search(link or "")
    return match.group(1).lower() if match else None


# ---- sitemaps -----------------------------------------------------------------

SITEMAP_INDEX = SITE + "/sitemap.xml"
SITEMAP_PRODUCT_PARTS = tuple("abcdefghi")   # product-sitemap-a.xml .. -i.xml (2026-10-28)

# public `type` -> sitemap file stem under /sitemap/au/
SITEMAP_TYPES = {
    "products": "product-sitemap-{part}",
    "categories": "category-sitemap",
    "collections": "collection-sitemap",
    "sellers": "seller-sitemap",
    "stores": "storelocation-sitemap",
    "content": "content-sitemap",
}


def sitemap_path(kind, part=None):
    stem = SITEMAP_TYPES[kind]
    if "{part}" in stem:
        stem = stem.format(part=part or SITEMAP_PRODUCT_PARTS[0])
    return f"/sitemap/au/{stem}.xml"
