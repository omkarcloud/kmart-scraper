"""Configuration for the Kmart Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT         port the API listens on (default 8000)
    KMART_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                 (default: none — direct). Product, search, category, brand,
                 seller-listing and review data come from Kmart's catalogue
                 and review services, which answer any connection. Kmart's
                 own pages (store details, seller shops, sitemaps) sit behind
                 Akamai and can start answering 403 to an IP that has sent a
                 lot of requests; if they do, set an Australian residential
                 proxy.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# Public keys every kmart.com.au page ships to the browser: the catalogue
# search index (Constructor.io) and the review widget (Yotpo).
KMART_CONSTRUCTOR_KEY = "key_GZTqlLr41FS2p7AY"
KMART_YOTPO_KEY = "SzVy7lws56AxMwq47Ufx69XAHnIA3zd0fBJNcbBG"

KMART_PROXY = os.environ.get("KMART_PROXY") or None


def kmart_proxy():
    """The proxy for one curl session (None = direct)."""
    return os.environ.get("KMART_PROXY") or None
