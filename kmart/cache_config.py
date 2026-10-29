"""Cache TTL per /kmart/* endpoint (cache.py, keyed on the validated
params). Kmart's catalogue is a live retail index: prices and clearance
flags move daily and per-state stock-outs (stateOOS) move within the day,
so product and listing rows are short; the structural indexes (category
tree, sellers, stores, sitemaps) move with site releases and live a day or
a week. The category tree, the seller index and the store index are each
ONE cached upstream build that every endpoint needing them slices
(api._tree / api._sellers / api._stores), so a client walking categories,
sellers or stores pays the upstream once.
"""
from datetime import timedelta

# Search / browse pages: prices, promos and stock flags change daily.
SEARCH_CACHE = timedelta(hours=2)
LISTING_CACHE = timedelta(hours=2)
# One product record (details / bulk): same volatility as a listing row.
PRODUCT_CACHE = timedelta(hours=2)
# Reviews accrue slowly; a new one is live on the next refresh.
REVIEWS_CACHE = timedelta(hours=12)
# Autocomplete suggestions are curated per term, not per hour.
SUGGESTIONS_CACHE = timedelta(hours=12)
# Bestsellers are a 14-day purchase-count pod; a day of caching is harmless.
BESTSELLERS_CACHE = timedelta(hours=6)
# The full category tree (2.3 MB upstream) moves with merchandising releases.
TREE_CACHE = timedelta(hours=24)
# Brand list: a facet over the whole index.
BRANDS_CACHE = timedelta(hours=24)
# Seller index (facet + sitemap join) and shop pages: sellers onboard weekly.
SELLERS_CACHE = timedelta(hours=24)
# The store index is 309 page fetches; stores open / change hours rarely.
STORES_CACHE = timedelta(days=7)
STORE_CACHE = timedelta(hours=24)
# Sitemaps are regenerated daily (their own lastmod stamps).
SITEMAP_CACHE = timedelta(hours=24)
